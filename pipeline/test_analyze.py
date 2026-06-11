# -*- coding: utf-8 -*-
"""Testes do motor — rodam no CI antes de qualquer commit de dados."""
import analyze

def test_acao_compra_forte():
    r = analyze.analisar_acao({"preco": 38.5, "dy": 0.138, "pl": 4.85, "pvp": 1.10,
                               "roe": 0.225, "payout": 0.67, "lpa": 7.94, "vpa": 35.0,
                               "liquidez": 8e8})
    assert r["veredito"] == "COMPRA FORTE", r["veredito"]

def test_acao_prejuizo_fica_em_branco():
    r = analyze.analisar_acao({"preco": 1.95, "dy": 0.0, "pl": -12.0, "pvp": 0.85,
                               "roe": -0.071, "payout": None, "lpa": -0.16, "vpa": 2.3,
                               "liquidez": 6e7})
    assert r["veredito"] is None and r["med3"] is None

def test_gordon_guardrail():
    # g >= r-2pp -> n.m., nunca número explosivo
    r = analyze.analisar_acao({"preco": 10, "dy": 0.01, "pl": 8, "pvp": 1.0,
                               "roe": 0.30, "payout": 0.1, "lpa": 1.25, "vpa": 10.0,
                               "liquidez": 1e7})
    assert r["gordon_nm"] is True and r["desc_gordon"] is None

def test_fii_trap():
    r = analyze.analisar_fii({"dy": 0.012, "pvp": 0.16, "preco": 22.1}, ntnb_real=0.07)
    assert r["trap"] is True
    r2 = analyze.analisar_fii({"dy": 0.178, "pvp": 0.55, "preco": 8.2}, ntnb_real=0.07)
    assert r2["trap"] is True
    r3 = analyze.analisar_fii({"dy": 0.089, "pvp": 0.95, "preco": 158.2}, ntnb_real=0.07)
    assert r3["trap"] is False and abs(r3["spread"] - 0.019) < 1e-9

def test_us_peg_penaliza_premium():
    aapl = analyze.analisar_us({"preco": 307, "pe": 36.9, "roe": 1.467,
                                "ev_ebitda": 28.5, "growth": 0.112, "dy": 0.003})
    nvda = analyze.analisar_us({"preco": 205, "pe": 31.2, "roe": 1.117,
                                "ev_ebitda": 25.8, "growth": 0.68, "dy": 0.001})
    assert aapl["veredito"] in ("CARO", "MUITO CARO")
    assert nvda["veredito"] == "ATRAENTE"

def test_us_sem_growth_ainda_funciona():
    r = analyze.analisar_us({"preco": 100, "pe": 20, "roe": 0.25,
                             "ev_ebitda": 12, "growth": None, "dy": 0.01})
    assert r["composto"] is not None and r["peg"] is None

if __name__ == "__main__":
    import sys, inspect
    mod = sys.modules["__main__"]
    fails = 0
    for name, fn in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith("test_"):
            try:
                fn(); print("ok ", name)
            except AssertionError as e:
                print("FAIL", name, e); fails += 1
    sys.exit(1 if fails else 0)
