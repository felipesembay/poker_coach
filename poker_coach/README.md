# Poker Coach

Plataforma de análise de MTT orientada a dados, com foco no ciclo
**sessão → diagnóstico → estudo dirigido**.

## Ambiente
O código usa sintaxe de **Python 3.10+** (`str | Path`). O `python3`
padrão do sistema pode apontar para uma versão mais antiga (ex.: Anaconda
com Python 3.9) — use um venv dedicado:
```bash
python3.12 -m venv .venv
.venv/bin/pip install streamlit pandas psycopg2-binary
```
Rode tudo com `.venv/bin/python` / `.venv/bin/streamlit` (ou ative o venv).

## Banco: PostgreSQL
Container `postgresql_olap` (Docker, IP de bridge `172.17.0.2:5432`,
user `postgres`/`airflow`), banco dedicado `poker_coach` (schema criado e
migrado automaticamente por `db.connect()` — nunca roda `psql` manual).
Banco `poker_coach_test` separado, mesmo container, usado pelos testes
(`tests/test_pushfold.py`) pra nunca escrever nos dados reais.

```bash
.venv/bin/python -m poker_coach.cli --db "postgresql://postgres:airflow@172.17.0.2:5432/poker_coach" import minha_sessao.txt
```

Migrado de um SQLite inicial (Fase 1) — `poker_coach/db.py` tem um
wrapper fino (`PGConnection`) que mantém a mesma interface
`conn.execute(sql_com_?, params)` que o resto do código (stats.py,
replay.py, pushfold/, icm_analyze.py) já usava, só trocando o driver por
baixo. Duas diferenças reais de comportamento entre os bancos que
exigiram mudança de lógica, não só de sintaxe (documentadas no topo de
`db.py`): Postgres aborta a transação inteira num INSERT que falha por
PK duplicada (SQLite não) — o import incremental usa `ON CONFLICT DO
NOTHING` + `rowcount` em vez de capturar exceção; e `AVG()` sobre coluna
INTEGER retorna `NUMERIC`/`Decimal` no Postgres (SQLite sempre devolvia
float) — os agregados de VPIP/PFR fazem cast explícito pra `::float`.

## O que já existe
- **Parsers**: PartyPoker (export real do "My Game" → Export Hands, validado
  contra 2013 mãos reais — conservação de fichas bate 100%, exceto ±1 chip em
  3 mãos por arredondamento de pote dividido do próprio PartyPoker) e
  PokerStars (formato padrão da sala, **ainda sem sample real para validar** —
  veja `samples/pokerstars/`).
- **Importador incremental**: mãos repetidas são ignoradas automaticamente.
- **Relatórios**: visão geral (VPIP, PFR, saldo em BB), ROI/ITM/ABI, mãos por torneio.
- **Primeiro detector de leak**: comportamento preflop com 8–20 BB por posição
  (fold/shove/raise, incl. folds em pote não aberto — spots de steal ignorados).
- **Motor de Push/Fold (Nash, chip EV)**: solver próprio (avaliador de mão +
  equity Monte Carlo + ponto fixo por fictitious play, sem tabela decorada —
  ver `poker_coach/pushfold/`). Aplica o equilíbrio às suas mãos reais de
  abertura (spots "unopened") e calcula EV perdido em BB.
  ```bash
  .venv/bin/python -m poker_coach.cli pushfold          # ou o botão no dashboard
  ```
  **Limitação importante**: o vilão modelado é sempre a BB (heads-up
  simplificado), pra manter o solver rápido. Isso é razoável perto do botão
  (BTN/CO/SB — pouca gente pode pagar atrás) mas **superestima o quanto você
  "devia" ter empurrado no UTG/MP**, onde na vida real vários jogadores ainda
  vão agir depois de você, não só a BB. Trate os números de UTG como teto
  otimista, não como leak confirmado — confie mais nos de BTN/CO/HJ/SB.

## Uso
```bash
# importar hand history (detecta a sala automaticamente)
.venv/bin/python -m poker_coach.cli import minha_sessao.txt

# registrar resultado de um torneio (posição e prêmio)
.venv/bin/python -m poker_coach.cli --db coach.db result partypoker 420849778 42 0

# relatório completo
.venv/bin/python -m poker_coach.cli report
```
> `--db` é opção global: vem **antes** do subcomando (`--db x.db import arquivo.txt`), não depois.

## Como exportar do PartyPoker
Cliente → menu **My Game** → **Export Hands** → escolha o período (até 40 dias) → Download.
O arquivo vem anonimizado (você = "Hero"), o que não afeta nada: o Coach analisa as SUAS decisões.

## Roadmap
- **Feito**: parsers (PartyPoker validado / PokerStars pendente de sample real),
  banco, dashboard, leak short-stack, motor de Push/Fold (Nash, chip EV, vilão=BB),
  Replayer, Modo Estudo, Evolução (acurácia real por mês).
  ICM (Malmuth-Harville) pra bolha/mesa final.
- **Próximo**: multiway no Push/Fold (mais de um vilão vivo — hoje só BB é
  modelado, distorce UTG/MP); range de call da BB re-resolvida sob ICM (hoje
  o motor de ICM usa a range de call em chip EV, só reavalia a decisão do
  herói — ver poker_coach/icm.py); ICM no Painel IA do Replayer e na
  Evolução; migração SQLite → PostgreSQL; camada de IA explicando cada
  erro em texto.

> Princípio de arquitetura: motores determinísticos calculam; a IA explica.

## Dashboard (Streamlit — multipágina com seções)
```bash
.venv/bin/streamlit run streamlit_app.py
```
Abre em http://localhost:8501. `streamlit_app.py` é só o roteador
(`st.navigation`, agrupa a barra lateral em seções); o conteúdo de cada
página fica em `app_pages/`:
- **⚙️ Configuração e Importação** (fora do grupo, primeira da lista) —
  caminho do banco, importar hand histories, registrar resultado de
  torneio: posição final + prêmio, **dinheiro ou ticket** (satélites
  costumam pagar bilhete, não $ — o Sharkscope não distingue isso, aqui
  dá pra marcar e ver o valor estimado separado do lucro em dinheiro).
- **Dashboard** (seção agrupada):
  - **🏠 Geral** — visão de conjunto (KPIs, evolução BB/$, torneios).
  - **💰 Lucro** — saldo em BB por horário/dia da semana (sempre
    disponível) + lucro em $ por dia/semana/mês/buy-in + resumo
    dinheiro vs ticket (precisa de resultado registrado).
  - **📈 ROI** — ROI por buy-in com insight automático (ex.: "seu ROI
    vira negativo acima de X, seu limite ideal hoje é Y").
  - **🎯 Push/Fold** — roda o solver de Nash sobre os spots de
    abertura, mostra precisão por faixa de stack e as piores mãos
    **com cartas renderizadas** (não mais texto cru "Jc As").
  - **📍 Posição** / **📊 Stack** — VPIP/PFR/saldo em BB por posição e
    por faixa de stack, com insight automático da pior/melhor faixa.
  - **🀄 ICM** — motor de Malmuth-Harville (`poker_coach/icm.py`, 8
    testes cobrindo conservação/forma fechada HU/efeito clássico de
    desconto). **Limitação real, não escondida**: ICM precisa do stack
    de TODO o campo do torneio + a premiação — a hand history só mostra
    sua mesa. Só é válido na mesa final, por isso a página exige
    premiação + confirmação explícita antes de calcular qualquer coisa.
    Mostra spots encontrados, EV perdido/ganho em $, Risk Premium, e uma
    tabela clicável que abre a mão direto no Replayer.
- **Replayer** (seção agrupada):
  - **🔁 Replayer** — busca de mãos (posição/stack/tag/favorito/showdown)
    + reconstrução completa passo a passo (mesa, stacks, pot, board,
    timeline por rua) + Painel IA (reusa o Push/Fold) + notas/tags/★.
    **Sem árvore de decisão com branches** (raise→fold/call/3bet): a
    hand history só grava a linha que realmente aconteceu, não
    contrafactuais — precisaria de um solver completo que não existe.
  - **🎓 Modo Estudo** — esconde sua decisão real, você responde
    Fold/Push (só essas duas — é só o que o motor julga), revela o
    Nash e o EV. Fica registrado em `quiz_log`.
  - **📅 Evolução** — o diferencial pedido: acurácia Push/Fold **real**
    por mês (recalculada sobre a hand history, não sintética) + ROI por
    mês + comparador de 2 períodos manual (sem detecção automática de
    "quando comecei a estudar").

Componentes compartilhados: `poker_coach/ui/cards.py` (renderização de
cartas como mini-cards HTML) e `poker_coach/ui/common.py` (conexão com o
banco, persistida entre páginas via `st.session_state`).
