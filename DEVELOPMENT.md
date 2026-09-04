# PokerLab — Guia de Desenvolvimento

Repositório com dois projetos independentes que rodam em paralelo:

| Projeto | Pasta | Porta |
|---|---|---|
| API FastAPI | `poker_coach/` | 8100 |
| Frontend TanStack Start | `pokerlab-ai-coach/` | 3000 (ou próxima livre — ver terminal) |

---

## Pré-requisitos

- **Python 3.12** com virtualenv em `poker_coach/.venv`
- **Bun** instalado globalmente (`curl -fsSL https://bun.sh/install | bash`)
- **PostgreSQL** acessível em `172.17.0.2:5432` — banco `poker_coach`

---

## 1. API (FastAPI)

```bash
cd poker_coach

# Ativar o virtualenv
source .venv/bin/activate

# Iniciar com hot-reload na porta 8100
.venv/bin/uvicorn api.main:app --reload --port 8100
```

- Swagger interativo: <http://localhost:8100/docs>
- OpenAPI JSON: <http://localhost:8100/openapi.json>

> **Nota:** a porta 8000 está ocupada por outro serviço nesta máquina; use sempre a 8100.

---

## 2. Frontend (TanStack Start + Vite)

```bash
cd poker_coach/pokerlab-ai-coach

# Instalar dependências (somente na primeira vez ou após atualizar package.json)
bun install

# Iniciar servidor de desenvolvimento
bun run dev
```

O frontend estará disponível em <http://localhost:3000> — **se essa porta já
estiver em uso** (comum nesta máquina), o Vite sobe automaticamente na
próxima livre (8080 → 8081 → 8082…). O terminal mostra a porta real logo
depois de "VITE ... ready", confira ali.

### Variável de ambiente

O arquivo `pokerlab-ai-coach/.env` já aponta para a API local:

```
VITE_API_URL=http://localhost:8100
```

Não é necessário alterar nada para rodar localmente.

---

## 3. Rodar os dois ao mesmo tempo

Abra dois terminais lado a lado:

**Terminal 1 — API:**
```bash
cd poker_coach
source .venv/bin/activate
.venv/bin/uvicorn api.main:app --reload --port 8100
```

**Terminal 2 — Frontend:**
```bash
cd poker_coach/pokerlab-ai-coach
bun run dev
```

---

## 4. Build de produção (frontend)

```bash
cd poker_coach/pokerlab-ai-coach
bun run build
```

O output fica em `.output/` e pode ser servido com:

```bash
bun run preview
```

---

## 5. Outros comandos úteis

| Comando | O que faz |
|---|---|
| `bun run lint` | ESLint em todo o frontend |
| `bun run format` | Prettier em todo o frontend |
| `pytest tests/` | Testes unitários da API (rodar de `poker_coach/`) |
