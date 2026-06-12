# -*- coding: utf-8 -*-
"""
fetch_reits.py — coleta dados dos US REITs (Finnhub) + UST 10 anos (Treasury).

Sem dependências externas (stdlib apenas). Modos:
  normal      : usado pelo run_reits.py (precisa de FINNHUB_KEY no ambiente)
  --fixtures  : lê fixtures/ em vez da rede (testes offline)
  --diagnose  : imprime as chaves disponíveis no /stock/metric para 1-2 tickers
                (rodar UMA vez ao vivo para travar o mapeamento de campos)

Notas de resiliência (mesmo padrão do parser Fundamentus):
  * Cada campo tem uma lista de chaves candidatas — se a Finnhub renomear,
    trocamos a lista, não o código.
  * FFO é aproximado (lucro líquido + D&A) via /stock/financials-reported.
    Se o endpoint/conceito faltar, payout_ffo = None ("s/d") — nunca alarme falso.
  * UST10Y: XML do Treasury (sem chave). Fallback: mês anterior; depois manual.
"""
import json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

FINNHUB = "https://finnhub.io/api/v1"
TREASURY_XML = ("https://home.treasury.gov/resource-center/data-chart-center/"
                "interest-rates/pages/xml?data=daily_treasury_yield_curve"
                "&field_tdr_date_value_month={ym}")

# ── Watchlist: 50 REITs (sem mortgage REITs — modelo de spread não se aplica) ──
WATCHLIST = {
    # Net lease
    "O":    ("Realty Income",        "Net lease"),
    "VICI": ("VICI Properties",      "Net lease"),
    "NNN":  ("NNN REIT",             "Net lease"),
    "WPC":  ("W. P. Carey",          "Net lease"),
    "ADC":  ("Agree Realty",         "Net lease"),
    "EPRT": ("Essential Properties", "Net lease"),
    # Industrial / logística
    "PLD":  ("Prologis",             "Industrial"),
    "REXR": ("Rexford Industrial",   "Industrial"),
    "STAG": ("STAG Industrial",      "Industrial"),
    "FR":   ("First Industrial",     "Industrial"),
    "EGP":  ("EastGroup Properties", "Industrial"),
    "TRNO": ("Terreno Realty",       "Industrial"),
    # Torres
    "AMT":  ("American Tower",       "Torres"),
    "CCI":  ("Crown Castle",         "Torres"),
    "SBAC": ("SBA Communications",   "Torres"),
    # Data centers
    "EQIX": ("Equinix",              "Data center"),
    "DLR":  ("Digital Realty",       "Data center"),
    # Saúde
    "WELL": ("Welltower",            "Saúde"),
    "VTR":  ("Ventas",               "Saúde"),
    "OHI":  ("Omega Healthcare",     "Saúde"),
    "DOC":  ("Healthpeak",           "Saúde"),
    "SBRA": ("Sabra Health Care",    "Saúde"),
    # Residencial (apartamentos + casas)
    "AVB":  ("AvalonBay",            "Residencial"),
    "EQR":  ("Equity Residential",   "Residencial"),
    "MAA":  ("Mid-America Apt.",     "Residencial"),
    "ESS":  ("Essex Property",       "Residencial"),
    "CPT":  ("Camden Property",      "Residencial"),
    "UDR":  ("UDR",                  "Residencial"),
    "INVH": ("Invitation Homes",     "Residencial"),
    "AMH":  ("American Homes 4 Rent","Residencial"),
    # Comunidades (manufactured housing)
    "ELS":  ("Equity LifeStyle",     "Comunidades"),
    "SUI":  ("Sun Communities",      "Comunidades"),
    # Varejo
    "SPG":  ("Simon Property",       "Varejo"),
    "KIM":  ("Kimco Realty",         "Varejo"),
    "REG":  ("Regency Centers",      "Varejo"),
    "FRT":  ("Federal Realty",       "Varejo"),
    "BRX":  ("Brixmor Property",     "Varejo"),
    "KRG":  ("Kite Realty",          "Varejo"),
    # Self-storage
    "PSA":  ("Public Storage",       "Self-storage"),
    "EXR":  ("Extra Space",          "Self-storage"),
    "CUBE": ("CubeSmart",            "Self-storage"),
    "NSA":  ("National Storage",     "Self-storage"),
    # Escritórios
    "BXP":  ("BXP (Boston Prop.)",   "Escritórios"),
    "KRC":  ("Kilroy Realty",        "Escritórios"),
    # Hotéis
    "HST":  ("Host Hotels",          "Hotéis"),
    "RHP":  ("Ryman Hospitality",    "Hotéis"),
    # Especializados
    "IRM":  ("Iron Mountain",        "Especializado"),
    "GLPI": ("Gaming & Leisure",     "Especializado"),
    "LAMR": ("Lamar Advertising",    "Especializado"),
    "WY":   ("Weyerhaeuser",         "Especializado"),
}

# ── Chaves candidatas no /stock/metric (ordem = preferência) ──────────────────
CANDIDATAS = {
    "dy":          ["dividendYieldIndicatedAnnual", "currentDividendYieldTTM",
                    "dividendYieldTTM"],
    "chg52w":      ["52WeekPriceReturnDaily"],
    "payout_gaap": ["payoutRatioTTM", "payoutRatioAnnual"],
    "div_ebitda":  ["netDebtToEbitdaAnnual", "totalDebtToEbitdaAnnual",
                    "totalDebt/totalEbitdaAnnual"],
    "div_pl":      ["totalDebt/totalEquityAnnual", "totalDebt/totalEquityQuarterly"],
}

# Conceitos US-GAAP candidatos (financials-reported) para o proxy de FFO
GAAP_NI  = ["NetIncomeLoss", "ProfitLoss",
            "NetIncomeLossAvailableToCommonStockholdersBasic"]
GAAP_DA  = ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
            "DepreciationAmortizationAndAccretionNet", "Depreciation"]
GAAP_DIV = ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends",
            "DividendsCommonStockCash", "PaymentsOfOrdinaryDividends"]

THROTTLE_S = 1.05   # 60 req/min na Finnhub free → ~1 req/s com folga


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "monitor-reits/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _pick(d, candidatas):
    for k in candidatas:
        v = d.get(k)
        if v is not None and v != "":
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _gaap_extrair(report, conceitos):
    """Procura um conceito GAAP nas seções ic/cf/bs do financials-reported."""
    data = (report or {}).get("report", {})
    for secao in ("ic", "cf", "bs"):
        for item in data.get(secao, []) or []:
            if item.get("concept") in conceitos:
                try:
                    return abs(float(item.get("value")))
                except (TypeError, ValueError):
                    pass
    return None


def fetch_ust10y(manual_fallback):
    """Yield do Treasury 10 anos (%, ex.: 4.31). XML mensal sem chave."""
    agora = datetime.now(timezone.utc)
    meses = [agora.strftime("%Y%m")]
    m, a = agora.month - 1 or 12, agora.year - (1 if agora.month == 1 else 0)
    meses.append(f"{a}{m:02d}")
    for ym in meses:
        try:
            req = urllib.request.Request(TREASURY_XML.format(ym=ym),
                                         headers={"User-Agent": "monitor-reits/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                xml = r.read().decode("utf-8", "ignore")
            vals = re.findall(r"BC_10YEAR[^>]*>([\d.]+)<", xml)
            if vals:
                return float(vals[-1]), "treasury"
        except Exception:
            continue
    return float(manual_fallback), "manual"


def fetch_reits(api_key, com_ffo=True, log=print):
    """Retorna lista de dicts crus por ticker (sem análise)."""
    saida = []
    for i, (tk, (nome, setor)) in enumerate(WATCHLIST.items(), 1):
        item = {"ticker": tk, "nome": nome, "setor": setor, "preco": None,
                "dy": None, "chg52w": None, "payout_gaap": None,
                "div_ebitda": None, "div_pl": None, "payout_ffo": None}
        try:
            q = _get_json(f"{FINNHUB}/quote?symbol={tk}&token={api_key}")
            item["preco"] = q.get("c") or None
            time.sleep(THROTTLE_S)
            m = _get_json(f"{FINNHUB}/stock/metric?symbol={tk}"
                          f"&metric=all&token={api_key}").get("metric", {})
            item["dy"]          = _pick(m, CANDIDATAS["dy"])
            item["chg52w"]      = _pick(m, CANDIDATAS["chg52w"])
            item["payout_gaap"] = _pick(m, CANDIDATAS["payout_gaap"])
            item["div_ebitda"]  = _pick(m, CANDIDATAS["div_ebitda"])
            item["div_pl"]      = _pick(m, CANDIDATAS["div_pl"])
            time.sleep(THROTTLE_S)
            if com_ffo:
                fr = _get_json(f"{FINNHUB}/stock/financials-reported?symbol={tk}"
                               f"&freq=annual&token={api_key}")
                rel = (fr.get("data") or [{}])[0]
                ni  = _gaap_extrair(rel, GAAP_NI)
                da  = _gaap_extrair(rel, GAAP_DA)
                dv  = _gaap_extrair(rel, GAAP_DIV)
                if ni is not None and da is not None and dv and (ni + da) > 0:
                    item["payout_ffo"] = round(dv / (ni + da), 3)
                time.sleep(THROTTLE_S)
        except urllib.error.HTTPError as e:
            log(f"  ⚠ {tk}: HTTP {e.code} — segue com parciais")
        except Exception as e:
            log(f"  ⚠ {tk}: {type(e).__name__}: {e}")
        saida.append(item)
        if i % 10 == 0:
            log(f"  {i}/{len(WATCHLIST)} tickers")
    return saida


def carregar_fixtures(pasta):
    with open(os.path.join(pasta, "reits_raw.json"), encoding="utf-8") as f:
        reits = json.load(f)
    with open(os.path.join(pasta, "ust10y.json"), encoding="utf-8") as f:
        ust = json.load(f)
    return reits, float(ust["ust10y"]), ust.get("fonte", "fixture")


def diagnose(api_key, tickers):
    """Roda 1x ao vivo: confirma quais chaves candidatas existem de verdade."""
    for tk in tickers:
        print(f"\n=== {tk} ===")
        m = _get_json(f"{FINNHUB}/stock/metric?symbol={tk}"
                      f"&metric=all&token={api_key}").get("metric", {})
        for campo, cands in CANDIDATAS.items():
            achadas = [c for c in cands if m.get(c) is not None]
            print(f"  {campo:12s}: {achadas or '— NENHUMA (me avise!)'}"
                  f"  valores={[m.get(c) for c in achadas]}")
        relevantes = sorted(k for k in m if re.search(
            r"yield|payout|debt|ebitda|52Week", k, re.I))
        print(f"  chaves relacionadas disponíveis: {relevantes}")
        time.sleep(THROTTLE_S)
        fr = _get_json(f"{FINNHUB}/stock/financials-reported?symbol={tk}"
                       f"&freq=annual&token={api_key}")
        rel = (fr.get("data") or [{}])[0]
        print(f"  FFO proxy → NI={_gaap_extrair(rel, GAAP_NI)}"
              f" D&A={_gaap_extrair(rel, GAAP_DA)}"
              f" Div pagos={_gaap_extrair(rel, GAAP_DIV)}")
        time.sleep(THROTTLE_S)


if __name__ == "__main__":
    if "--diagnose" in sys.argv:
        key = os.environ.get("FINNHUB_KEY")
        if not key:
            sys.exit("Defina FINNHUB_KEY no ambiente. Ex.: "
                     "FINNHUB_KEY=xxx python pipeline/fetch_reits.py --diagnose O PLD")
        tks = [a for a in sys.argv[2:] if not a.startswith("-")] or ["O", "PLD"]
        diagnose(key, tks)
    else:
        print("Use via run_reits.py, ou --diagnose para o teste ao vivo.")
