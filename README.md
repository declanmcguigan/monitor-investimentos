# Monitor · Ações & FIIs & US

Pipeline diário (GitHub Actions) + dashboard estático (GitHub Pages).

- `pipeline/` — busca Fundamentus (BR), Finnhub (US), BCB/AwesomeAPI (macro+FX) e roda os modelos
  (Bazin/Graham/Gordon, spread NTN-B + trap FII, composto 4 fatores US).
- `docs/` — dashboard (Pages) + `data.json`/`history.json` gerados.
- `data/holdings.json` — suas posições ({"PETR4": 100}). `data/classificacao.json` — blocos/setores.
- Segredo necessário: `FINNHUB_KEY` (Settings ▸ Secrets ▸ Actions).
- Pages: Settings ▸ Pages ▸ Deploy from branch ▸ `main` /docs.

Teste local: `python pipeline/run.py --fixtures fixtures/` e sirva `docs/`.
