# -*- coding: utf-8 -*-
"""Orquestrador: busca BR + US + macro, roda análises, grava docs/data.json
e acrescenta snapshot diário em data/history.jsonl (para tendências).

Uso:
  python pipeline/run.py                       # produção (APIs reais; FINNHUB_KEY no env)
  python pipeline/run.py --fixtures fixtures/  # offline/testes
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(__file__))
import analyze  # noqa: E402
import fetch_br  # noqa: E402
import fetch_us  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = ROOT / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", default=None)
    args = ap.parse_args()
    fx = args.fixtures

    # ---------------- classificações + holdings ----------------
    classif = json.loads((DATA / "classificacao.json").read_text(encoding="utf-8"))
    holdings_path = DATA / "holdings.json"
    holdings = json.loads(holdings_path.read_text(encoding="utf-8")) if holdings_path.exists() else {}

    # ---------------- macro ----------------
    macro = fetch_us.fetch_macro(fixture_dir=fx)
    ntnb = macro.get("ntnb_real") or 0.07

    # ---------------- BR ----------------
    acoes_raw, fiis_raw = fetch_br.fetch(fixture_dir=fx)
    acoes = []
    for r in acoes_raw:
        r["bloco"] = classif["acoes"].get(r["ticker"], "A CLASSIFICAR (NOVOS)")
        r["qtd"] = holdings.get(r["ticker"], 0)
        acoes.append(analyze.analisar_acao(r))
    fiis = []
    for r in fiis_raw:
        r["bloco"] = classif["fiis"].get(r["ticker"], r.get("segmento") or "OUTROS")
        r["qtd"] = holdings.get(r["ticker"], 0)
        fiis.append(analyze.analisar_fii(r, ntnb))

    # ---------------- US ----------------
    us_raw = fetch_us.fetch(api_key=os.environ.get("FINNHUB_KEY"), fixture_dir=fx)
    us = []
    for r in us_raw:
        if "erro" in r and len(r) <= 2:
            us.append(r)
            continue
        r["qtd"] = holdings.get(r["ticker"], 0)
        us.append(analyze.analisar_us(r))

    # ---------------- saúde dos dados (lição StatusInvest!) ----------------
    # Se o universo encolher de repente (fonte filtrada/quebrada), FALHA o run
    # em vez de publicar dados quebrados — o dashboard mantém o snapshot anterior.
    MINIMOS = {"acoes": 400, "fiis": 200, "us_validos": 30}
    us_validos = sum(1 for u in us if u.get("veredito") is not None or u.get("preco"))
    def _null_rate(rows_, key):
        if not rows_:
            return 1.0
        return sum(1 for r in rows_ if r.get(key) is None) / len(rows_)
    saude = {
        "n_acoes": len(acoes), "n_fiis": len(fiis), "n_us": len(us),
        "us_validos": us_validos,
        "null_preco_acoes": round(_null_rate(acoes, "preco"), 3),
        "null_dy_fiis": round(_null_rate(fiis, "dy"), 3),
        "fx_ok": macro.get("usdbrl") is not None,
        "alertas": [],
    }
    fixtures_mode = bool(fx)
    if not fixtures_mode:  # em testes/fixtures os mínimos não se aplicam
        problemas = []
        if len(acoes) < MINIMOS["acoes"]:
            problemas.append(f"ações: {len(acoes)} < mínimo {MINIMOS['acoes']} (fonte filtrada/quebrada?)")
        if len(fiis) < MINIMOS["fiis"]:
            problemas.append(f"FIIs: {len(fiis)} < mínimo {MINIMOS['fiis']}")
        if us_validos < MINIMOS["us_validos"]:
            problemas.append(f"US válidos: {us_validos} < mínimo {MINIMOS['us_validos']}")
        if saude["null_preco_acoes"] > 0.2:
            problemas.append(f"{saude['null_preco_acoes']:.0%} das ações sem preço")
        if problemas:
            print("FALHA DE SAÚDE — dados NÃO publicados:")
            for p in problemas:
                print("  ✗", p)
            sys.exit(1)
    if not saude["fx_ok"]:
        saude["alertas"].append("câmbio indisponível; usando último valor do dashboard")

    # ---------------- saída principal ----------------
    agora = dt.datetime.now(dt.timezone.utc)
    payload = {
        "gerado_em": agora.isoformat(timespec="seconds"),
        "macro": macro,
        "premissas": analyze.PREMISSAS,
        "saude": saude,
        "acoes": acoes,
        "fiis": fiis,
        "us": us,
    }
    DOCS.mkdir(exist_ok=True)
    (DOCS / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---------------- snapshot histórico (holdings + vereditos) ----------------
    snap = {
        "data": agora.date().isoformat(),
        "usdbrl": macro.get("usdbrl"),
        "acoes": {a["ticker"]: {"v": a.get("veredito"), "m": a.get("med3"), "p": a.get("preco")}
                  for a in acoes if a.get("qtd", 0) > 0 or a.get("veredito") in ("COMPRA FORTE", "COMPRA")},
        "fiis": {f["ticker"]: {"s": f.get("spread"), "p": f.get("preco")}
                 for f in fiis if f.get("qtd", 0) > 0 or (f.get("spread") or 0) > 0.02},
        "us": {u["ticker"]: {"v": u.get("veredito"), "c": u.get("composto"), "p": u.get("preco")}
               for u in us if u.get("qtd", 0) > 0 or u.get("veredito") == "ATRAENTE"},
    }
    hist = DATA / "history.jsonl"
    lines = hist.read_text(encoding="utf-8").splitlines() if hist.exists() else []
    lines = [l for l in lines if not l.startswith('{"data": "%s"' % snap["data"])
             and not l.startswith('{"data":"%s"' % snap["data"])]
    lines.append(json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    hist.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # histórico recente também vai pro dashboard (últimos 90 snapshots)
    recent = [json.loads(l) for l in lines[-90:]]
    (DOCS / "history.json").write_text(
        json.dumps(recent, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"OK: {len(acoes)} ações, {len(fiis)} FIIs, {len(us)} US | "
          f"USD/BRL {macro.get('usdbrl')} | snapshots {len(lines)}")


if __name__ == "__main__":
    main()
