# -*- coding: utf-8 -*-
"""
run_reits.py — orquestra a coleta + análise e grava docs/reits.json.

Uso:
  FINNHUB_KEY=xxx python pipeline/run_reits.py
  python pipeline/run_reits.py --fixtures fixtures/      (offline / testes)

Independente do pipeline principal: escreve apenas docs/reits.json.
Gate de saúde: se <40/50 REITs válidos, sai com código 1 e NÃO sobrescreve.
Lê data/holdings.json (se existir) para QTD/VALOR — mesmos tickers US.
"""
import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_reits import fetch_reits, fetch_ust10y, carregar_fixtures  # noqa: E402
from analyze_reits import PREMISSAS_REITS, analisar_reit, gate_saude  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(RAIZ, "docs", "reits.json")
HOLDINGS = os.path.join(RAIZ, "data", "holdings.json")


def main():
    if "--fixtures" in sys.argv:
        pasta = sys.argv[sys.argv.index("--fixtures") + 1]
        crus, ust10y, fonte = carregar_fixtures(pasta)
        print(f"[fixtures] {len(crus)} REITs · UST10Y={ust10y} ({fonte})")
    else:
        key = os.environ.get("FINNHUB_KEY")
        if not key:
            sys.exit("FINNHUB_KEY ausente no ambiente.")
        com_ffo = os.environ.get("REITS_FFO", "0") == "1"  # diagnóstico provou vazio no free tier
        ust10y, fonte = fetch_ust10y(PREMISSAS_REITS["ust10y_manual"])
        print(f"UST10Y = {ust10y}% (fonte: {fonte})")
        crus = fetch_reits(key, com_ffo=com_ffo)

    reits = [analisar_reit(r, ust10y) for r in crus]
    ok, validos, alertas = gate_saude(reits)
    for a in alertas:
        print(f"⚠ {a}")
    if not ok:
        sys.exit(1)  # preserva o reits.json anterior

    qtd = {}
    if os.path.exists(HOLDINGS):
        try:
            with open(HOLDINGS, encoding="utf-8") as f:
                qtd = {k: v for k, v in json.load(f).items()
                       if isinstance(v, (int, float))}
        except Exception as e:
            print(f"⚠ holdings.json ilegível ({e}) — seguindo sem carteira")
    for r in reits:
        r["qtd"] = qtd.get(r["ticker"], 0)
        r["valor_usd"] = (round(r["qtd"] * r["preco"], 2)
                          if r["qtd"] and r.get("preco") else 0)

    payload = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "ust10y": round(ust10y, 2),
        "ust10y_fonte": fonte,
        "premissas": PREMISSAS_REITS,
        "saude": {"validos": validos, "total": len(reits), "alertas": alertas},
        "reits": sorted(reits, key=lambda r: (r["spread"] is None,
                                              -(r["spread"] or -99))),
    }
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    contagem = {}
    for r in reits:
        contagem[r["veredito"]] = contagem.get(r["veredito"], 0) + 1
    print(f"✔ {SAIDA} gravado · {validos}/{len(reits)} válidos · {contagem}")


if __name__ == "__main__":
    main()
