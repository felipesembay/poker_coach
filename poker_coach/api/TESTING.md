# PokerLab API — guia de teste manual

## Rodar

```bash
cd poker_coach
.venv/bin/uvicorn api.main:app --reload --port 8100
```

- Swagger interativo (testa direto no navegador, tem botão "Try it out"
  em cada endpoint): **http://localhost:8100/docs**
- OpenAPI JSON cru: http://localhost:8100/openapi.json
- Porta 8000 está ocupada por outro serviço (container Docker não
  relacionado) e 8010 é usada por outra coisa nesta máquina — por isso
  **8100**, não os defaults comuns de FastAPI.

Banco: Postgres em `172.17.0.2:5432/poker_coach` (fixo em
`api/deps.py::DSN` — mesma instância que o dashboard Streamlit usa,
dados reais, sem sandbox separado. Endpoints de escrita alteram o banco
de verdade).

---

## O que está implementado vs. o que é aproximado

Antes de testar, para não estranhar números:

| Área | Status |
|---|---|
| Push/Fold (spots, summary, range-grid) | **Real** — solver de Nash, sem tabela decorada |
| Push/Fold Treinador | **Real** na decisão/EV. `explanation` é **templada** a partir dos números, não é texto gerado por IA |
| ICM | **Real** na matemática (Malmuth-Harville). `category` (Mesa Final/Bolha/Satélite) é **heurística** derivada de payouts × jogadores restantes, não uma classificação do motor. **"Hero Call" não existe** — análise pós-flop não é coberta. Exige `confirmed=true` (mesa final confirmada) senão dá 400 |
| Replayer | **Real**, direto do banco. Sem árvore de decisão com branches (só a linha que realmente aconteceu) |
| Mãos / Tags / Favoritos | **Real**. `color` das tags é heurística por palavra-chave. Favoritos só cobre mãos — "Estudo"/"Drill" do mock não existem como módulo ainda |

---

## Push/Fold

### `GET /api/pushfold/spots`
Lista de spots de abertura já analisados pelo Nash.

```bash
curl "http://localhost:8100/api/pushfold/spots?bb_min=5&bb_max=25&limit=5"
```
```json
[{
  "site": "partypoker", "hand_id": "17801118972836rtktes4ukf",
  "tournament_id": "420849778", "spot": "Abertura (UTG)", "position": "UTG",
  "stack": "2.6 BB", "hero_cards": "2h Kh", "taken": "Fold", "correct": "All-in",
  "ev": 1.27, "ev_lost_bb": 1.27
}]
```
Leva alguns segundos (roda o solver sobre todas as mãos na faixa). Real:
260 spots analisados na base atual, 87.9 BB de EV perdido total.

### `GET /api/pushfold/summary`
Mesmo relatório, agregado por posição.
```bash
curl "http://localhost:8100/api/pushfold/summary"
```

### `GET /api/pushfold/range-grid`
Grid 13×13 de EV por classe de mão — o gráfico que faltava na página
(equivalente ao heatmap do ICMizer).
```bash
curl "http://localhost:8100/api/pushfold/range-grid?effective_bb=10&pot_bb=1.5"
```
`grid` é um dict de 169 entradas (`"AA": 5.58, "72o": -1.52, ...`).

### `GET /api/pushfold/trainer/next`
Sorteia uma mão pro Modo Estudo — **não revela** a decisão certa.
`mode=open` (padrão): herói é o primeiro a agir (abertura). `mode=facing_shove`:
um vilão já deu all-in antes do herói decidir (call ou fold).
```bash
curl "http://localhost:8100/api/pushfold/trainer/next"
curl "http://localhost:8100/api/pushfold/trainer/next?mode=facing_shove"
```

### `POST /api/pushfold/trainer/answer`
Responde e recebe o gabarito. Usa `site`/`hand_id` da resposta do `next`
e o mesmo `mode` (senão o servidor tenta reavaliar como o modo errado
e devolve 404). `decision` é `"Fold"`/`"All-in"` em `mode=open` e
`"Fold"`/`"Call"` em `mode=facing_shove`.
```bash
curl -X POST "http://localhost:8100/api/pushfold/trainer/answer" \
  -H "Content-Type: application/json" \
  -d '{"site":"partypoker","hand_id":"<hand_id do /next>","mode":"open","decision":"Fold"}'

curl -X POST "http://localhost:8100/api/pushfold/trainer/answer" \
  -H "Content-Type: application/json" \
  -d '{"site":"partypoker","hand_id":"<hand_id do /next?mode=facing_shove>","mode":"facing_shove","decision":"Call"}'
```
Grava em `quiz_log` de verdade — some no `/trainer/stats` depois.

### `GET /api/pushfold/trainer/stats`
```bash
curl "http://localhost:8100/api/pushfold/trainer/stats"
```


---

## ICM

### `GET /api/icm/tournaments`
Lista torneios importados + se já têm premiação salva.
```bash
curl "http://localhost:8100/api/icm/tournaments"
```

### `PUT /api/icm/tournaments/{site}/{tournament_id}/payouts`
Salva a premiação (1º lugar primeiro).
```bash
curl -X PUT "http://localhost:8100/api/icm/tournaments/partypoker/421930167/payouts" \
  -H "Content-Type: application/json" \
  -d '{"prizes":[10.71,6.00,3.00]}'
```

### `GET /api/icm/tournaments/{site}/{tournament_id}/payouts`
```bash
curl "http://localhost:8100/api/icm/tournaments/partypoker/421930167/payouts"
```

### `GET /api/icm/spots`
**Exige `confirmed=true`** — sem isso dá 400 de propósito (a hand
history não mostra o campo inteiro do torneio, só a sua mesa; sem
confirmação explícita o número seria inventado).
```bash
# sem confirmed -> 400 esperado
curl "http://localhost:8100/api/icm/spots?site=partypoker&tournament_id=421930167"

# com confirmed -> calcula
curl "http://localhost:8100/api/icm/spots?site=partypoker&tournament_id=421930167&confirmed=true&max_table_size=9"
```
Tournament com dados reais pra testar sem precisar salvar premiação
antes: `421967292` (já tem `[8.0, 5.0, 3.0]` salvo).

### `GET /api/icm/hand/{site}/{hand_id}`
Mesmo motor de `/spots`, só que pra uma mão só — usado pelo painel de
ICM do Replayer. Mesmas exigências: `confirmed=true` + premiação salva
pro torneio, senão devolve `in_scope=false` com o motivo.
```bash
curl "http://localhost:8100/api/icm/hand/partypoker/1785800859037q5nrtxdqvm8?confirmed=true"
```

---

## Replayer

### `GET /api/replayer/search`
Filtros combináveis: `site`, `tournament_id`, `position`, `bb_min`,
`bb_max`, `n_players`, `result` (`win`/`loss`), `tag`, `q` (busca livre
em hand_id/cartas/tags/nota), `favorite`, `showdown`, `all_in` (os três
últimos são tri-state: omitido = todos, `true`/`false` = só sim/não),
`date_from`, `date_to`.
```bash
curl "http://localhost:8100/api/replayer/search?showdown=true&limit=5"
curl "http://localhost:8100/api/replayer/search?tournament_id=421930167"
```

### `GET /api/replayer/{site}/{hand_id}`
Estado completo: assentos, passo a passo (pot/stacks/board a cada
ação), Painel IA, nota, tags, favorito.
```bash
curl "http://localhost:8100/api/replayer/partypoker/1785800859037q5nrtxdqvm8"
```
Confira a conservação de fichas: `sum(steps[-1].stacks_after.values())`
tem que bater com `sum(seat.starting_stack)`.

---

## Mãos / Tags / Favoritos

### `GET /api/hands`
Hand browser paginado. Filtros: `site`, `position`, `bb_min`, `bb_max`,
`tag`, `favorite_only`, `showdown_only`, `date_from`, `date_to`,
`limit`, `offset`.
```bash
curl "http://localhost:8100/api/hands?limit=10"
```

### `PUT /api/hands/{site}/{hand_id}/favorite`
```bash
curl -X PUT "http://localhost:8100/api/hands/partypoker/<hand_id>/favorite" \
  -H "Content-Type: application/json" -d '{"favorite": true}'
```

### `PUT /api/hands/{site}/{hand_id}/note`
```bash
curl -X PUT "http://localhost:8100/api/hands/partypoker/<hand_id>/note" \
  -H "Content-Type: application/json" -d '{"text": "revisar depois"}'
```

### `PUT /api/hands/{site}/{hand_id}/tags`
Substitui todas as tags da mão pela lista enviada.
```bash
curl -X PUT "http://localhost:8100/api/hands/partypoker/<hand_id>/tags" \
  -H "Content-Type: application/json" -d '{"tags": ["Push/Fold", "Bad Beat"]}'
```

### `GET /api/tags`
```bash
curl "http://localhost:8100/api/tags"
```

### `GET /api/favorites`
```bash
curl "http://localhost:8100/api/favorites"
```

---

## Já testado ponta a ponta nesta sessão
Todos os 17 endpoints acima rodaram contra o banco real (não só
import/sintaxe): números do Push/Fold batendo com o dashboard Streamlit
(260 spots, 87.9 BB perdido), gate do ICM recusando sem `confirmed=true`
e calculando certo com, conservação de fichas do Replayer batendo
(800=800), e o ciclo completo favorito→nota→tags→leitura de volta nos
três endpoints diferentes (hands, replayer, tags, favorites) todos
concordando entre si. Os dados de teste escritos durante essa validação
foram revertidos do banco real depois.
