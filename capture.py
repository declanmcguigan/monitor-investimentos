# -*- coding: utf-8 -*-
"""FASE 2 — captura de respostas reais para travar os parsers.
Rode na sua máquina:  python capture.py SUA_CHAVE_FINNHUB
Gera capture_out/ — me envie os arquivos gerados (zip da pasta)."""
import json, sys, pathlib, urllib.request

out = pathlib.Path("capture_out"); out.mkdir(exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0"}

def get(url, binary=False):
    req = urllib.request.Request(url, headers=HEADERS)
    data = urllib.request.urlopen(req, timeout=60).read()
    return data if binary else data.decode("latin-1", errors="replace")

print("1/4 Fundamentus ações…")
(out/"fundamentus_acoes.html").write_text(get("https://www.fundamentus.com.br/resultado.php"), encoding="utf-8")
print("2/4 Fundamentus FIIs…")
(out/"fundamentus_fii.html").write_text(get("https://www.fundamentus.com.br/fii_resultado.php"), encoding="utf-8")

print("3/4 Macro (BCB + câmbio)…")
macro_raw = {}
for nome, serie in {"selic":432, "ipca_12m":13522}.items():
    try: macro_raw[nome] = json.loads(get(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json"))
    except Exception as e: macro_raw[nome] = {"erro": str(e)}
try: macro_raw["usdbrl"] = json.loads(get("https://economia.awesomeapi.com.br/json/last/USD-BRL"))
except Exception as e: macro_raw["usdbrl"] = {"erro": str(e)}
(out/"macro_raw.json").write_text(json.dumps(macro_raw, ensure_ascii=False, indent=1), encoding="utf-8")

print("4/4 Finnhub (3 tickers de amostra: AAPL, ORCL, BRK-B)…")
key = sys.argv[1] if len(sys.argv) > 1 else input("Chave Finnhub: ").strip()
fh = {}
for t in ["AAPL", "ORCL", "BRK-B"]:
    fh[t] = {}
    for nome, path in [("profile", f"/stock/profile2?symbol={t}"),
                       ("metrics", f"/stock/metric?symbol={t}&metric=all"),
                       ("quote", f"/quote?symbol={t}")]:
        try: fh[t][nome] = json.loads(get(f"https://finnhub.io/api/v1{path}&token={key}"))
        except Exception as e: fh[t][nome] = {"erro": str(e)}
(out/"finnhub_sample.json").write_text(json.dumps(fh, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nPronto! Me envie a pasta capture_out/ (ou um zip dela).")
