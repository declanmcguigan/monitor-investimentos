# -*- coding: utf-8 -*-
"""test_reits.py — casos de calibração do motor de REITs (roda no CI antes do pipeline)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_reits import analisar_reit, gate_saude, PREMISSAS_REITS

UST = 4.30
FALHAS = []


def caso(nome, item, veredito, spread=None, dy_liq=None, armadilhas=None):
    r = analisar_reit(dict({"ticker": "T", "nome": "t", "setor": "s",
                            "preco": 50.0, "chg52w": 0.0, "payout_ffo": None,
                            "div_ebitda": None, "payout_gaap": None,
                            "div_pl": None}, **item), UST)
    probs = []
    if r["veredito"] != veredito:
        probs.append(f"veredito={r['veredito']} (esperado {veredito})")
    if spread is not None and r["spread"] != spread:
        probs.append(f"spread={r['spread']} (esperado {spread})")
    if dy_liq is not None and r["dy_liq"] != dy_liq:
        probs.append(f"dy_liq={r['dy_liq']} (esperado {dy_liq})")
    if armadilhas is not None and r["armadilhas"] != armadilhas:
        probs.append(f"armadilhas={r['armadilhas']} (esperado {armadilhas})")
    status = "ok" if not probs else "FALHOU: " + "; ".join(probs)
    print(f"  [{'✔' if not probs else '✘'}] {nome}: {status}")
    if probs:
        FALHAS.append(nome)


print("Calibração do motor (UST10Y = 4.30):")
# 1. COMPRA limpa: DY 6.0 → spread 1.70, líq 4.20
caso("COMPRA limpa", {"dy": 6.0}, "COMPRA", spread=1.70, dy_liq=4.20,
     armadilhas=[])
# 2. Fronteira exata do spread_compra (1.5 inclusive)
caso("COMPRA na fronteira 1.5pp", {"dy": 5.8}, "COMPRA", spread=1.50)
# 3. OBSERVAR: DY 5.0 → spread 0.70
caso("OBSERVAR", {"dy": 5.0}, "OBSERVAR", spread=0.70)
# 4. CARO: DY 3.5 → spread -0.80
caso("CARO", {"dy": 3.5}, "CARO", spread=-0.80)
# 5. Armadilha DY-via-queda: DY 9, preço -40% em 52s → CUIDADO
caso("CUIDADO: DY via queda", {"dy": 9.0, "chg52w": -40.0}, "CUIDADO",
     spread=4.70, armadilhas=["DY via queda"])
# 6. DY alto MAS sem queda → segue COMPRA (armadilha exige as duas condições)
caso("DY alto sem queda → COMPRA", {"dy": 7.5, "chg52w": -10.0}, "COMPRA",
     armadilhas=[])
# 7. Payout FFO 120% → CUIDADO
caso("CUIDADO: payout FFO", {"dy": 6.0, "payout_ffo": 1.20}, "CUIDADO",
     armadilhas=["Payout FFO alto"])
# 8. Payout FFO saudável (85%) não dispara
caso("Payout FFO 85% ok", {"dy": 6.0, "payout_ffo": 0.85}, "COMPRA",
     armadilhas=[])
# 9. Dívida/EBITDA 8.5x → CUIDADO mesmo em zona OBSERVAR
caso("CUIDADO: alavancagem em zona OBSERVAR", {"dy": 5.0, "div_ebitda": 8.5},
     "CUIDADO", armadilhas=["Alavancagem alta"])
# 9b. Fallback D/E: sem dív/EBITDA (free tier), D/E 2.4 → CUIDADO
caso("CUIDADO: alavancagem via D/E (fallback)", {"dy": 6.0, "div_pl": 2.4},
     "CUIDADO", armadilhas=["Alavancagem alta"])
# 9c. D/E saudável (0.73, caso real O) não dispara
caso("D/E 0.73 ok (caso O)", {"dy": 6.0, "div_pl": 0.73}, "COMPRA",
     armadilhas=[])
# 9d. Se dív/EBITDA existe e está ok, D/E alto NÃO dispara (EBITDA tem prioridade)
caso("Dív/EBITDA ok prevalece sobre D/E", {"dy": 6.0, "div_ebitda": 5.0,
     "div_pl": 2.4}, "COMPRA", armadilhas=[])
# 10. Armadilha em zona CARA continua CARO (não 'rebaixa' o que já é caro)
caso("CARO mesmo com armadilha", {"dy": 3.0, "div_ebitda": 9.0}, "CARO")
# 11. Sem DY → s/d
caso("Sem DY → s/d", {"dy": None}, "s/d")
# 12. Duas armadilhas simultâneas
caso("Duas armadilhas", {"dy": 9.5, "chg52w": -30.0, "payout_ffo": 1.1},
     "CUIDADO", armadilhas=["DY via queda", "Payout FFO alto"])

print("Gate de saúde:")
bons = [{"preco": 10.0, "dy": 5.0}] * 41 + [{"preco": None, "dy": None}] * 9
ok, validos, _ = gate_saude([analisar_reit(dict({"ticker": "T", "nome": "t",
    "setor": "s", "chg52w": 0, "payout_ffo": None, "div_ebitda": None,
    "payout_gaap": None, "div_pl": None}, **b), UST) for b in bons])
print(f"  [{'✔' if ok and validos == 41 else '✘'}] 41/50 válidos → passa "
      f"(validos={validos})")
if not (ok and validos == 41):
    FALHAS.append("gate-passa")

ruins = bons[:39] + [{"preco": None, "dy": None}] * 11
ok2, validos2, alertas2 = gate_saude([analisar_reit(dict({"ticker": "T",
    "nome": "t", "setor": "s", "chg52w": 0, "payout_ffo": None,
    "div_ebitda": None, "payout_gaap": None, "div_pl": None}, **b), UST)
    for b in ruins])
print(f"  [{'✔' if not ok2 else '✘'}] 39/50 válidos → falha e preserva "
      f"({alertas2[0] if alertas2 else 'sem alerta?'})")
if ok2:
    FALHAS.append("gate-falha")

w = PREMISSAS_REITS["withholding"]
print(f"  [{'✔' if w == 0.30 else '✘'}] withholding = {w}")

if FALHAS:
    sys.exit(f"\n✘ {len(FALHAS)} caso(s) falharam: {FALHAS}")
print("\n✔ Todos os casos de calibração passaram.")
