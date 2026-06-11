# -*- coding: utf-8 -*-
"""US stocks via Finnhub (free: 60 calls/min, fundamentos amplos)
   + Macro via BCB SGS (SELIC, IPCA) e câmbio USD/BRL via AwesomeAPI.

Finnhub por ticker (2 chamadas):
  /stock/profile2?symbol=X       -> name, finnhubIndustry, marketCap
  /stock/metric?symbol=X&metric=all -> peTTM/peBasicExclExtraTTM, roeTTM,
     evToEbitdaTTM (ou similares), dividendYieldIndicatedAnnual,
     epsGrowth5Y, netProfitMarginTTM, price (via quote se necessário)
  /quote?symbol=X                -> c (preço atual)  [3a chamada]
"""
import json
import time
import pathlib

FINNHUB = "https://finnhub.io/api/v1"

WATCHLIST = [
    "NVDA","AAPL","GOOG","MSFT","AMZN","META","AVGO","TSLA","BRK-B","WMT",
    "LLY","JPM","XOM","V","JNJ","MU","MA","COST","ORCL","NFLX",
    "CVX","ABBV","PLTR","PG","HD","BAC","KO","CAT","AMD","GE",
    "CSCO","MRK","LRCX","AMAT","PM","RTX","UNH","MS","GS","TMUS",
    "IBM","WFC","MCD","LIN","GEV","INTC","PEP","VZ","AXP","T",
]


def load_watchlist():
    """data/watchlist_us.json se existir; senão a lista embutida (50)."""
    import pathlib
    p = pathlib.Path(__file__).resolve().parent.parent / "data" / "watchlist_us.json"
    if p.exists():
        try:
            wl = json.loads(p.read_text(encoding="utf-8")).get("tickers") or []
            if wl:
                return wl
        except Exception:
            pass
    return WATCHLIST


def _g(d, *keys):
    """primeiro valor não-nulo entre aliases de campo"""
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return None


def parse_us(profile, metrics, quote, ticker):
    m = metrics.get("metric", {}) if isinstance(metrics, dict) else {}
    pe = _g(m, "peTTM", "peBasicExclExtraTTM", "peNormalizedAnnual")
    roe = _g(m, "roeTTM", "roeRfy")
    ev = _g(m, "evEbitdaTTM", "evToEbitdaTTM")  # confirmado: evEbitdaTTM (NUNCA usar EV/FCF aqui)
    growth = _g(m, "epsGrowth5Y", "epsGrowth3Y")
    dy = _g(m, "dividendYieldIndicatedAnnual", "currentDividendYieldTTM")
    margem = _g(m, "netProfitMarginTTM", "netProfitMargin5Y")
    preco = (quote or {}).get("c") or _g(m, "price")
    # normalizações: Finnhub publica ROE/growth/DY/margem em PONTOS PERCENTUAIS
    def frac(x):
        return (x / 100.0) if isinstance(x, (int, float)) else None
    return {
        "ticker": ticker,
        "nome": (profile or {}).get("name"),
        "setor": (profile or {}).get("finnhubIndustry"),
        "preco": preco,
        "pe": pe,
        "roe": frac(roe),
        "ev_ebitda": ev,
        "growth": frac(growth),
        "dy": frac(dy),
        "margem": frac(margem),
        "mktcap": (profile or {}).get("marketCapitalization"),
    }


def fetch(api_key=None, fixture_dir=None, watchlist=None, pace=1.1):
    wl = watchlist or load_watchlist()
    out = []
    if fixture_dir:
        fx = pathlib.Path(fixture_dir)
        raw = json.loads((fx / "finnhub_us.json").read_text(encoding="utf-8"))
        for t in wl:
            r = raw.get(t)
            if not r:
                out.append({"ticker": t, "erro": "sem fixture"})
                continue
            out.append(parse_us(r.get("profile"), r.get("metrics"), r.get("quote"), t))
        return out
    import urllib.request, urllib.error
    def get(path):
        url = f"{FINNHUB}{path}&token={api_key}" if "?" in path else f"{FINNHUB}{path}?token={api_key}"
        # ritmo: 60 chamadas/min no free => ~1 chamada/seg, pausando ANTES de cada chamada
        time.sleep(pace)
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:  # estourou o limite: espera a janela renovar e tenta 1x
                time.sleep(20)
                with urllib.request.urlopen(url, timeout=30) as r:
                    return json.loads(r.read().decode())
            raise
    for t in wl:
        try:
            prof = get(f"/stock/profile2?symbol={t}")
            met = get(f"/stock/metric?symbol={t}&metric=all")
            quo = get(f"/quote?symbol={t}")
            out.append(parse_us(prof, met, quo, t))
        except Exception as e:  # noqa
            out.append({"ticker": t, "erro": str(e)})
    return out


# ------------------------------- MACRO -------------------------------
BCB_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json"
SERIES = {"selic": 432, "ipca_12m": 13522}
FX_URL = "https://economia.awesomeapi.com.br/json/last/USD-BRL"


def fetch_macro(fixture_dir=None, ntnb_manual=0.07):
    if fixture_dir:
        fx = pathlib.Path(fixture_dir)
        raw = json.loads((fx / "macro.json").read_text(encoding="utf-8"))
        return raw
    import urllib.request
    def get(url):
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode())
    out = {}
    for nome, serie in SERIES.items():
        try:
            v = get(BCB_SGS.format(serie=serie))
            out[nome] = float(v[0]["valor"].replace(",", ".")) / 100
        except Exception:
            out[nome] = None
    try:
        fxj = get(FX_URL)
        out["usdbrl"] = float(fxj["USDBRL"]["bid"])
    except Exception:
        out["usdbrl"] = None
    if out["usdbrl"] is None:  # fallback: BCB SGS 1 (dólar comercial venda)
        try:
            v = get(BCB_SGS.format(serie=1))
            out["usdbrl"] = float(v[0]["valor"].replace(",", "."))
        except Exception:
            pass
    out["ntnb_real"] = ntnb_manual  # juro real NTN-B: input manual/config
    return out
