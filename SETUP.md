# Setup (Fase 3) — uma vez só, ~10 minutos

## 1. Chave Finnhub (grátis)
1. https://finnhub.io → Sign up grátis → copie a **API Key** do painel.

## 2. Criar o repositório
1. https://github.com/new → nome ex. `monitor-investimentos` → **Public** (Pages grátis exige repo público; suas posições NÃO vão ao repo — ficam no navegador) → Create.
2. No repo: *uploading an existing file* → arraste TODO o conteúdo desta pasta
   (inclusive `.github/` — se o upload web ignorar pastas ocultas, use o GitHub Desktop
   ou `git push` pelo terminal). Commit.

## 3. Segredo da API
Settings ▸ Secrets and variables ▸ Actions ▸ **New repository secret**
- Name: `FINNHUB_KEY`  |  Secret: sua chave do passo 1.

## 4. Permissão de escrita do bot
Settings ▸ Actions ▸ General ▸ Workflow permissions ▸ **Read and write permissions** ▸ Save.

## 5. Ativar o site (Pages)
Settings ▸ Pages ▸ Source: **Deploy from a branch** ▸ Branch `main`, pasta **/docs** ▸ Save.
A URL aparece ali (ex.: `https://SEUUSER.github.io/monitor-investimentos/`).
Adicione à tela inicial do iPhone.

## 6. Primeira execução
Actions ▸ *Atualizar dados do monitor* ▸ **Run workflow**. ~2 min depois, abra a URL.
A partir daí roda sozinho seg–sex 06:30 BRT.

## Rotina (rara)
- **Posições:** direto no dashboard, aba 💼 CARTEIRA ▸ "Adicionar posição". Salvas no aparelho (localStorage); repita no iPhone se quiser lá também.
- **Watchlist US:** edite `WATCHLIST` em `pipeline/fetch_us.py`.
- **Premissas** (piso Bazin, CoE, pesos): `PREMISSAS` em `pipeline/analyze.py`.
- **NTN-B real:** `ntnb_manual` em `fetch_us.py ▸ fetch_macro` (ou me peça p/ automatizar via Tesouro).

## Proteções embutidas
- Se a fonte BR “encolher” (tipo o incidente das 101 linhas), o run **falha e não publica**
  — o site continua com os últimos dados bons.
- Testes do motor rodam antes de cada atualização.
- `⚠ desatualizado` aparece no site se os dados tiverem >48h.
