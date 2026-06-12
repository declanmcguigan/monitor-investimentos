# Guia do Monitor — Setup & Uso (v2 · Fase 4)

Pipeline diário (GitHub Actions) + dashboard estático (GitHub Pages).
Cobre: Ações BR (Bazin/Graham/Gordon), FIIs (spread vs NTN-B + armadilhas),
US Stocks (composto 4 fatores, 503 nomes) e **US REITs (spread vs UST10Y,
50 nomes)** — novo na Fase 4.

---

## 1. Setup inicial (uma vez só, ~10 min)

1. **Chave Finnhub (grátis):** https://finnhub.io → Sign up → copie a API Key.
2. **Repositório:** https://github.com/new → ex. `monitor-investimentos` →
   Private → Create. Suba TODO o conteúdo (inclusive `.github/` — se o upload
   web ignorar pastas ocultas, use GitHub Desktop ou `git push`).
3. **Segredo:** Settings ▸ Secrets and variables ▸ Actions ▸ New repository
   secret → Name `FINNHUB_KEY`, Secret = sua chave.
4. **Permissão do bot:** Settings ▸ Actions ▸ General ▸ Workflow permissions ▸
   **Read and write** ▸ Save.
5. **Site:** Settings ▸ Pages ▸ Deploy from a branch ▸ `main` /docs ▸ Save.
   Adicione a URL à tela inicial do iPhone.
6. **Primeira execução:** Actions ▸ rode os dois workflows manualmente
   (*Atualizar dados do monitor* e *Atualizar US REITs*).

## 2. Agenda automática (e por que o horário é "torto")

| Workflow                    | Cron (UTC)      | BRT   | Repescagem |
|-----------------------------|-----------------|-------|------------|
| Atualizar dados do monitor  | `23 9 * * 1-5`  | 06:23 | 07:23      |
| Atualizar US REITs          | `23 9 * * 1-5`  | 06:23 | 07:23      |

Crons do GitHub são *best-effort*: horários cheios (:00/:30) atrasam 15–60 min
ou são derrubados. Por isso minuto 23 + uma segunda entrada de repescagem —
os pipelines são idempotentes: se a 1ª rodou, a 2ª não comita nada.

## 3. Rotina (rara)

- **Posições:** edite `data/holdings.json` no próprio GitHub (lápis ▸ commit).
  Um arquivo só para tudo: `{"PETR4": 100, "AAPL": 10, "O": 25}`.
- **Watchlist US Stocks:** `WATCHLIST` em `pipeline/fetch_us.py`.
- **Watchlist US REITs:** `WATCHLIST` em `pipeline/fetch_reits.py`
  (ticker → nome, setor). Sem mREITs — o modelo de spread não se aplica.
- **Premissas BR/US:** `PREMISSAS` em `pipeline/analyze.py`.
- **Premissas REITs:** `PREMISSAS_REITS` em `pipeline/analyze_reits.py`
  (spread de COMPRA 1,5pp, armadilhas, retenção 30%, UST10Y manual).
- **NTN-B real:** `ntnb_manual` em `fetch_us.py ▸ fetch_macro`.

## 4. Como ler os vereditos

**Ações BR:** composto Bazin + Graham + Gordon (MÉD 3) com gate de qualidade.
**FIIs:** spread do DY sobre a NTN-B com detecção de armadilha.
**US Stocks:** composto 4 fatores (PEG, EV/EBITDA, ROE vs custo de capital, P/L).
**US REITs:** spread = DY bruto − UST10Y. COMPRA ≥ +1,5pp · OBSERVAR ≥ +0,5pp ·
abaixo disso CARO. Qualquer armadilha (DY via queda, payout FFO > 90%,
dívida/EBITDA > 7x) rebaixa para CUIDADO. A coluna **DY líq.** (= bruto × 0,70,
retenção do IRS para não-residentes — Brasil e EUA não têm tratado) é
informativa e não entra no veredito. P/L e PEG **não** valem para REITs:
a depreciação esmaga o lucro GAAP — por isso a aba própria.

## 5. Quando algo der errado

1. **Dashboard "desatualizado" (⚠ no topo):** dados com mais de 48h.
   Vá ao Actions e veja a última execução.
2. **Nenhuma execução no horário:** cron drift do GitHub (ver §2) — a
   repescagem deve cobrir; se nem ela rodou, Run workflow manual.
3. **Execução vermelha:** abra o log. Se for o **gate de saúde**
   ("universo encolheu" / "<40/50 REITs válidos"), os dados anteriores foram
   preservados de propósito — o problema é a fonte (Fundamentus/Finnhub),
   não o pipeline. O alerta também aparece no topo do dashboard.
4. **Campos s/d nos REITs:** rode o diagnóstico ao vivo e me mande a saída:
   `FINNHUB_KEY=xxx python3 pipeline/fetch_reits.py --diagnose O PLD`
5. **Teste local sem rede:** `python pipeline/run.py --fixtures fixtures/`
   e `python pipeline/run_reits.py --fixtures fixtures/`, depois sirva `docs/`.

## 6. Páginas do site

- `index.html` — Ações · FIIs · US Stocks · Carteira/Simulador
- `reits.html` — US REITs (spread vs UST10Y)
- `guia.html` — este guia
