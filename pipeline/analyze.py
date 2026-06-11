# -*- coding: utf-8 -*-
"""
Motor de análise — porta a lógica exata da planilha Monitor Ações & FII.

Ações (BR):  Bazin + Graham + Gordon -> MÉD 3 descontos + filtro qualidade -> VEREDITO
FIIs:        Spread DY - NTN-B real + detecção de armadilha (trap)
US Stocks:   Composto 4 fatores (PEG, EV/EBITDA, RIM, P/L) -> VEREDITO
"""
import math

# ----------------------------- premissas (editáveis) -----------------------------
PREMISSAS = {
    "bazin_floor_br": 0.065,     # piso DY Bazin BR (6,5%)
    "bazin_floor_us": 0.04,      # piso DY Bazin US (4%)
    "coe_us": 0.10,              # custo de capital US
    "risk_rate_br": 0.145,       # taxa de desconto Gordon (SELIC ~)
    "w_peg": 0.35, "w_ev": 0.25, "w_rim": 0.25, "w_pl": 0.15,
    "min_liquidez": 500_000,     # filtro qualidade: liquidez média diária mínima
    "fii_trap_pvp": 0.70,        # P/VP abaixo disso = possível armadilha
    "fii_trap_dy": 0.16,         # DY acima disso = possível armadilha
}


def _n(v):
    """número seguro: None/''/NaN -> None"""
    if v is None or v == "":
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


# ================================ AÇÕES (BR) ================================
def analisar_acao(row, p=PREMISSAS):
    """row: dict com preco, dy, pl, pvp, roe, payout, lpa, vpa, liquidez,
    cresc_5a (opcional), setor/bloco. Retorna dict com valuations + veredito."""
    preco = _n(row.get("preco"))
    dy = _n(row.get("dy"))            # fração (0.065 = 6,5%)
    pl = _n(row.get("pl"))
    pvp = _n(row.get("pvp"))
    roe = _n(row.get("roe"))          # fração
    payout = _n(row.get("payout"))    # fração
    lpa = _n(row.get("lpa"))
    vpa = _n(row.get("vpa"))
    liq = _n(row.get("liquidez")) or 0
    out = dict(row)

    # DPA = preco * dy
    dpa = preco * dy if (preco and dy) else None

    # ---- Bazin: valuation = DPA / piso ----
    val_bazin = (dpa / p["bazin_floor_br"]) if (dpa and dpa > 0) else None
    desc_bazin = ((val_bazin - preco) / val_bazin) if (val_bazin and preco) else None

    # ---- Graham: sqrt(22.5 * LPA * VPA), só com lucro+patrimônio positivos ----
    val_graham = None
    if lpa and vpa and lpa > 0 and vpa > 0:
        val_graham = math.sqrt(22.5 * lpa * vpa)
    desc_graham = ((val_graham - preco) / val_graham) if (val_graham and preco) else None

    # ---- Gordon: DPA*(1+g)/r, guarda-corpo: g >= r-2pp -> n.m.; clamp de g ----
    val_gordon = None
    g = None
    if payout is not None and roe is not None:
        g = max(0.0, (1 - min(payout, 1.0)) * roe)  # crescimento retido, nunca negativo
    r = p["risk_rate_br"]
    if dpa and dpa > 0 and g is not None:
        if g >= r - 0.02:
            val_gordon = "n.m."  # não significativo (guarda-corpo)
        else:
            val_gordon = dpa * (1 + g) / (r - g)
    desc_gordon = None
    if isinstance(val_gordon, float) and val_gordon > 0 and preco:
        desc_gordon = (val_gordon - preco) / val_gordon
        # guarda-corpo extra: descarta distorções extremas (> +/-300%)
        if desc_gordon < -3.0:
            desc_gordon = None
            val_gordon = "n.m."

    # ---- MÉD 3: média dos descontos disponíveis ----
    descontos = [d for d in (desc_bazin, desc_graham, desc_gordon) if d is not None]
    med3 = sum(descontos) / len(descontos) if descontos else None
    consenso = (len(descontos) == 3 and all(d > 0 for d in descontos))

    # ---- Filtro qualidade ----
    qualidade = (
        dy is not None and dy > 0
        and payout is not None and 0 <= payout <= 1
        and liq > p["min_liquidez"]
    )

    # ---- Veredito ----
    if med3 is None:
        veredito = None
    elif consenso and qualidade and med3 > 0.20:
        veredito = "COMPRA FORTE"
    elif med3 > 0.10 and qualidade:
        veredito = "COMPRA"
    elif med3 < 0:
        veredito = "CARO"
    else:
        veredito = "NEUTRO"

    out.update({
        "dpa": dpa, "val_bazin": val_bazin, "desc_bazin": desc_bazin,
        "val_graham": val_graham, "desc_graham": desc_graham,
        "val_gordon": val_gordon if isinstance(val_gordon, float) else None,
        "gordon_nm": val_gordon == "n.m.",
        "desc_gordon": desc_gordon, "med3": med3,
        "consenso": consenso, "qualidade": qualidade, "veredito": veredito,
    })
    return out


# ================================== FIIs ==================================
def analisar_fii(row, ntnb_real, p=PREMISSAS):
    """row: dict com preco, dy (fração), pvp, caixa, cagr_div, cagr_cota,
    patrimonio, cotistas, liquidez, gestao, bloco."""
    dy = _n(row.get("dy"))
    pvp = _n(row.get("pvp"))
    out = dict(row)
    spread = (dy - ntnb_real) if dy is not None else None
    # trap: P/VP muito baixo OU DY irreal
    trap = bool(
        (pvp is not None and 0 < pvp < p["fii_trap_pvp"])
        or (dy is not None and dy > p["fii_trap_dy"])
    )
    out.update({"spread": spread, "trap": trap})
    return out


# ================================ US STOCKS ================================
def _score_peg(pe, growth):
    """growth em fração (0.15 = 15% a.a.)."""
    if not pe or pe <= 0 or not growth or growth <= 0:
        return None
    peg = pe / (growth * 100)
    if peg <= 0.8: return 1.0
    if peg <= 1.2: return 0.75
    if peg <= 1.8: return 0.45
    if peg <= 2.5: return 0.2
    return 0.0


def _score_ev(ev):
    if not ev or ev <= 0:
        return None
    if ev <= 10: return 1.0
    if ev <= 15: return 0.7
    if ev <= 22: return 0.4
    if ev <= 30: return 0.2
    return 0.0


def _score_rim(roe, coe):
    if roe is None:
        return None
    e = roe - coe
    if e >= 0.15: return 1.0
    if e >= 0.08: return 0.8
    if e >= 0.02: return 0.55
    if e >= -0.02: return 0.35
    return 0.1


def _score_pl(pe):
    if not pe or pe <= 0:
        return None
    if pe <= 18: return 1.0
    if pe <= 28: return 0.65
    if pe <= 40: return 0.35
    if pe <= 60: return 0.15
    return 0.05


def analisar_us(row, p=PREMISSAS):
    """row: dict com preco, pe, roe, ev_ebitda, growth (fração), dy, margem, setor."""
    pe = _n(row.get("pe"))
    roe = _n(row.get("roe"))
    ev = _n(row.get("ev_ebitda"))
    growth = _n(row.get("growth"))
    dy = _n(row.get("dy"))
    preco = _n(row.get("preco"))
    out = dict(row)

    s_peg = _score_peg(pe, growth)
    s_ev = _score_ev(ev)
    s_rim = _score_rim(roe, p["coe_us"])
    s_pl = _score_pl(pe)
    peg = (pe / (growth * 100)) if (pe and pe > 0 and growth and growth > 0) else None

    num = den = 0.0
    for s, w in ((s_peg, p["w_peg"]), (s_ev, p["w_ev"]), (s_rim, p["w_rim"]), (s_pl, p["w_pl"])):
        if s is not None:
            num += s * w
            den += w
    composto = (num / den) if den else None

    if composto is None:
        veredito = None
    elif composto >= 0.7:
        veredito = "ATRAENTE"
    elif composto >= 0.5:
        veredito = "RAZOÁVEL"
    elif composto >= 0.3:
        veredito = "CARO"
    else:
        veredito = "MUITO CARO"

    # sinal de renda secundário (Bazin US) — só p/ DY >= 2%
    desc_bazin = None
    sinal_renda = "não é renda"
    if dy is not None and dy >= 0.02 and preco:
        val = (preco * dy) / p["bazin_floor_us"]
        desc_bazin = (val - preco) / val if val else None
        if desc_bazin is not None:
            sinal_renda = ("renda: barata" if desc_bazin > 0.10
                           else "renda: cara" if desc_bazin < 0 else "renda: justa")

    out.update({
        "peg": peg, "s_peg": s_peg, "s_ev": s_ev, "s_rim": s_rim, "s_pl": s_pl,
        "composto": composto, "veredito": veredito,
        "desc_bazin": desc_bazin, "sinal_renda": sinal_renda,
    })
    return out
