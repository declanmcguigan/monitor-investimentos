# -*- coding: utf-8 -*-
"""Busca dados BR (ações + FIIs) do Fundamentus. Sem login, universo completo.

Ações:  https://www.fundamentus.com.br/resultado.php
FIIs:   https://www.fundamentus.com.br/fii_resultado.php

Em modo fixture, lê HTML salvo em fixtures/ (para testes offline e para
travar o parser contra respostas reais capturadas na Fase 2).
"""
import re
import json
import pathlib

HEADERS = {"User-Agent": "Mozilla/5.0 (monitor pessoal; uso não comercial)"}
URL_ACOES = "https://www.fundamentus.com.br/resultado.php"
URL_FII = "https://www.fundamentus.com.br/fii_resultado.php"


def _num_br(s):
    """'1.234,56' -> 1234.56 ; '12,3%' -> 0.123 ; '' -> None"""
    if s is None:
        return None
    s = re.sub(r"<[^>]+>", "", str(s)).strip()
    if not s or s in ("-", "--"):
        return None
    pct = s.endswith("%")
    s = s.replace("%", "").replace(".", "").replace(",", ".")
    try:
        v = float(s)
        return v / 100 if pct else v
    except ValueError:
        return None


def _parse_table(html):
    """Extrai linhas <tr> da tabela de resultados do Fundamentus."""
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, re.S | re.I)
    raw = body.group(1) if body else html
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", raw, re.S | re.I):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if tds:
            rows.append([re.sub(r"<[^>]+>", "", td).strip() for td in tds])
    return rows


def _headers(html):
    """rótulos <th> da tabela, normalizados"""
    head = re.search(r"<thead[^>]*>(.*?)</thead>", html, re.S | re.I)
    if not head:
        return []
    ths = re.findall(r"<th[^>]*>(.*?)</th>", head.group(1), re.S | re.I)
    return [re.sub(r"<[^>]+>", "", th).strip().lower() for th in ths]


def _colmap_acoes(html):
    """mapeia nome de campo -> índice de coluna pelo cabeçalho; fallback p/ ordem clássica."""
    hs = _headers(html)
    def find(*pats):
        for i, h in enumerate(hs):
            for p in pats:
                if p in h:
                    return i
        return None
    m = {
        "preco": find("cota"), "pl": find("p/l"), "pvp": find("p/vp"),
        "dy": find("yield"), "roe": find("roe"),
        "liq": find("liq.2", "liq. 2", "liq.2meses"),
        "cresc": find("cresc"), "mrg": find("mrg. líq", "mrg.liq", "mrg líq"),
    }
    fallback = {"preco": 1, "pl": 2, "pvp": 3, "dy": 5, "roe": 16, "liq": 17, "cresc": 20, "mrg": 13}
    for k, v in m.items():
        if v is None:
            m[k] = fallback[k]
    return m


# Ordem clássica do resultado.php usada como fallback (ver _colmap_acoes)
def parse_acoes(html):
    out = []
    cm = _colmap_acoes(html)
    for t in _parse_table(html):
        if len(t) <= max(cm.values()):
            continue
        ticker = t[0].upper()
        if not re.match(r"^[A-Z]{4}[0-9]{1,2}[A-Z]?$", ticker):
            continue
        preco = _num_br(t[cm["preco"]]); pl = _num_br(t[cm["pl"]]); pvp = _num_br(t[cm["pvp"]])
        dy = _num_br(t[cm["dy"]]); roe = _num_br(t[cm["roe"]]); liq2m = _num_br(t[cm["liq"]])
        cresc = _num_br(t[cm["cresc"]]); mrgliq = _num_br(t[cm["mrg"]])
        # derivados p/ Graham: LPA = preco/PL ; VPA = preco/PVP
        lpa = (preco / pl) if (preco and pl and pl != 0) else None
        vpa = (preco / pvp) if (preco and pvp and pvp != 0) else None
        # payout estimado = DY * PL (DY = DPA/P; PL = P/LPA; DY*PL = DPA/LPA)
        payout = (dy * pl) if (dy is not None and pl and pl > 0) else None
        out.append({
            "ticker": ticker, "preco": preco, "dy": dy, "pl": pl, "pvp": pvp,
            "roe": roe, "margem": mrgliq, "lpa": lpa, "vpa": vpa,
            "payout": payout, "liquidez": liq2m, "cresc_5a": cresc,
        })
    return out


def _colmap_fii(html):
    hs = _headers(html)
    def find(*pats):
        for i, h in enumerate(hs):
            for p in pats:
                if p in h:
                    return i
        return None
    m = {
        "segmento": find("segmento"), "preco": find("cota"),
        "dy": find("dividend yield", "div. yield", "dy"),
        "pvp": find("p/vp"), "mercado": find("valor de mercado"),
        "liq": find("liquidez"), "imoveis": find("imóveis", "imoveis"),
        "vac": find("vac"),
    }
    fallback = {"segmento": 1, "preco": 2, "dy": 4, "pvp": 5, "mercado": 6,
                "liq": 7, "imoveis": 8, "vac": 12}
    for k, v in m.items():
        if v is None:
            m[k] = fallback[k]
    return m


def parse_fiis(html):
    out = []
    cm = _colmap_fii(html)
    for t in _parse_table(html):
        if len(t) <= max(cm.values()):
            continue
        ticker = t[0].upper()
        if not re.match(r"^[A-Z]{4}11[A-Z]?$", ticker):
            continue
        out.append({
            "ticker": ticker, "segmento": t[cm["segmento"]], "preco": _num_br(t[cm["preco"]]),
            "dy": _num_br(t[cm["dy"]]), "pvp": _num_br(t[cm["pvp"]]),
            "patrimonio": _num_br(t[cm["mercado"]]), "liquidez": _num_br(t[cm["liq"]]),
            "imoveis": _num_br(t[cm["imoveis"]]), "vacancia": _num_br(t[cm["vac"]]),
        })
    return out


def fetch(fixture_dir=None):
    if fixture_dir:
        fx = pathlib.Path(fixture_dir)
        acoes_html = (fx / "fundamentus_acoes.html").read_text(encoding="utf-8")
        fii_html = (fx / "fundamentus_fii.html").read_text(encoding="utf-8")
    else:
        import urllib.request
        def get(url):
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=60).read().decode("latin-1")
        acoes_html = get(URL_ACOES)
        fii_html = get(URL_FII)
    return parse_acoes(acoes_html), parse_fiis(fii_html)


if __name__ == "__main__":
    import sys
    fx = sys.argv[1] if len(sys.argv) > 1 else None
    a, f = fetch(fx)
    print(json.dumps({"acoes": len(a), "fiis": len(f)}))
