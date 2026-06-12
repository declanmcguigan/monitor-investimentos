# -*- coding: utf-8 -*-
"""
analyze_reits.py — modelo "FII, edição US":
  spread bruto = DY bruto − UST10Y  (pontos percentuais)
  DY líquido   = DY bruto × (1 − withholding 30%)  — coluna informativa, NÃO
                 entra no veredito (decisão da conversa: veredito no bruto).

Armadilhas (qualquer uma rebaixa COMPRA → CUIDADO):
  1. "DY via queda"     : DY alto + preço −25% ou pior em 52s
  2. "Payout FFO alto"  : dividendos / (LL + D&A) > 90%   (s/d se proxy faltar)
  3. "Alavancagem alta" : dívida/EBITDA > 7,0x            (s/d se faltar)

Vereditos: COMPRA / OBSERVAR / CARO / CUIDADO  (+ "s/d" se sem DY ou preço)
"""

PREMISSAS_REITS = {
    "spread_compra":    1.5,    # pp acima do UST10Y para COMPRA
    "spread_observar":  0.5,    # pp para OBSERVAR
    "dy_armadilha":     7.0,    # % — DY a partir do qual investigamos a queda
    "queda_armadilha":  -25.0,  # % em 52 semanas
    "payout_ffo_max":   0.90,
    "div_ebitda_max":   7.0,    # REIT saudável costuma rodar 5–6x (se disponível)
    "div_pl_max":       2.0,    # fallback: dívida/PL — free tier não tem dív/EBITDA
    "withholding":      0.30,   # IRS sobre dividendos p/ não-residente (sem tratado BR-EUA)
    "ust10y_manual":    4.30,   # fallback se o XML do Treasury falhar
}


def analisar_reit(item, ust10y, p=PREMISSAS_REITS):
    """Recebe o dict cru do fetcher; devolve enriquecido com análise."""
    r = dict(item)
    r["ust10y"] = round(ust10y, 2)
    dy = r.get("dy")

    if dy is None or r.get("preco") is None:
        r.update({"dy_liq": None, "spread": None, "armadilhas": [],
                  "veredito": "s/d"})
        return r

    r["dy_liq"] = round(dy * (1 - p["withholding"]), 2)
    spread = round(dy - ust10y, 2)
    r["spread"] = spread

    armadilhas = []
    chg = r.get("chg52w")
    if dy >= p["dy_armadilha"] and chg is not None and chg <= p["queda_armadilha"]:
        armadilhas.append("DY via queda")
    pf = r.get("payout_ffo")
    if pf is not None and pf > p["payout_ffo_max"]:
        armadilhas.append("Payout FFO alto")
    de = r.get("div_ebitda")
    dpl = r.get("div_pl")
    if de is not None:
        if de > p["div_ebitda_max"]:
            armadilhas.append("Alavancagem alta")
    elif dpl is not None and dpl > p["div_pl_max"]:
        armadilhas.append("Alavancagem alta")
    r["armadilhas"] = armadilhas

    if spread >= p["spread_compra"]:
        r["veredito"] = "CUIDADO" if armadilhas else "COMPRA"
    elif spread >= p["spread_observar"]:
        r["veredito"] = "CUIDADO" if armadilhas else "OBSERVAR"
    else:
        r["veredito"] = "CARO"
    return r


def gate_saude(reits, minimo_validos=40):
    """Mesmo princípio do gate do pipeline principal: se o universo encolher
    inesperadamente, a execução falha e o reits.json anterior é preservado."""
    validos = sum(1 for r in reits
                  if r.get("preco") is not None and r.get("dy") is not None)
    alertas = []
    ok = validos >= minimo_validos
    if not ok:
        alertas.append(f"Apenas {validos}/{len(reits)} REITs com preço+DY "
                       f"(mínimo {minimo_validos}) — dados anteriores preservados")
    return ok, validos, alertas
