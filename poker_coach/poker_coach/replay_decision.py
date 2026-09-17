"""Integração do Decision Analyzer (Etapas 2-5) com o Replayer (Etapa 6).

Converte um passo de `ReplayHand` (já reconstruído por `replay.py`, que
já rastreia pot/stacks/board por ação — reaproveitado aqui, não
reimplementado) numa chamada de `context.analyze_decision()`.

Reconstrução do "quanto falta pagar" (seção 7.1 do plano — não contar
2x): reprocessa só as ações da RUA ATUAL antes do passo do hero,
somando contribuições por jogador. O nível mais alto atingido é o valor
que precisa ser igualado; `hero_call_cost` vem de context/pot_odds a
partir da diferença entre esse nível e o quanto o hero já colocou nessa
mesma rua — nunca do valor bruto da aposta.

Vilão sem mão revelada (sem showdown) é modelado como `EquityOpponent`
sem `cards`/`range_classes` — "qualquer duas cartas" (ver docstring de
`equity_engine.py`). Não inventamos range a partir de posição/estilo —
isso ficaria pra uma etapa futura, com um modelo de range explícito e
documentado.
"""
from __future__ import annotations

from . import context
from .equity_engine import EquityOpponent
from .replay import ReplayHand

CONTRIBUTING_ACTIONS = ("post_sb", "post_bb", "post_ante", "call", "bet", "raise", "allin")
NON_DECISION_ACTIONS = ("post_sb", "post_bb", "post_ante", "deal", "resolve", "win", "show")


class ReplayDecisionError(ValueError):
    """Não dá pra montar uma análise de decisão pra esse passo do replay."""


def _active_players_before(rh: ReplayHand, step_index: int) -> set[str]:
    folded = {s.player for s in rh.steps[:step_index] if s.action == "fold"}
    return set(rh.seat_order) - folded


def _street_state_before(rh: ReplayHand, step_index: int) -> tuple[dict[str, int], int, bool, int]:
    """(contribuições por jogador nessa rua, nível atual, último nível-alvo
    foi all-in, nº de vezes que uma ação VOLUNTÁRIA — bet/raise/allin —
    subiu o nível) considerando só as ações da MESMA rua antes do passo.

    Blind/ante não contam como "voluntary_changes": pagar a diferença
    do BB é o spot clássico de abertura (contexto 1 do plano — push/fold),
    não "estar enfrentando uma aposta". `call` (limp) também não conta —
    ninguém subiu o nível, só igualou.
    """
    street = rh.steps[step_index].street
    start = rh.street_first_index.get(street, 0)
    contributions: dict[str, int] = {}
    level = 0
    level_is_all_in = False
    voluntary_changes = 0
    for s in rh.steps[start:step_index]:
        if s.action in CONTRIBUTING_ACTIONS:
            contributions[s.player] = contributions.get(s.player, 0) + s.amount
            if contributions[s.player] > level:
                level = contributions[s.player]
                level_is_all_in = s.all_in
                if s.action in ("bet", "raise", "allin"):
                    voluntary_changes += 1
    return contributions, level, level_is_all_in, voluntary_changes


def analyze_hero_step(
    rh: ReplayHand,
    step_index: int,
    *,
    opponents_override: list[EquityOpponent] | None = None,
    equity_simulation_method: str = "auto",
    equity_iterations: int | None = None,
    equity_seed: int | None = None,
) -> context.DecisionAnalysis:
    """Monta o contexto da decisão do hero no passo `step_index` (a partir
    do estado JÁ calculado por `replay.py`) e delega pro Decision Analyzer
    (`context.analyze_decision`, Etapa 5)."""
    if not rh.hero or not rh.hero_cards:
        raise ReplayDecisionError("mão sem herói/cartas do herói conhecidas")
    if step_index < 0 or step_index >= len(rh.steps):
        raise ReplayDecisionError(f"step_index fora do intervalo: {step_index}")

    step = rh.steps[step_index]
    if step.player != rh.hero:
        raise ReplayDecisionError(
            f"passo {step_index} não é uma ação do hero (é de {step.player!r})"
        )
    if step.action in NON_DECISION_ACTIONS:
        raise ReplayDecisionError(f"ação '{step.action}' não é uma decisão de poker analisável")

    street = step.street
    contributions, level, level_is_all_in, voluntary_changes = _street_state_before(rh, step_index)
    hero_in = contributions.get(rh.hero, 0)

    active = _active_players_before(rh, step_index)
    num_players_in_hand = max(len(active), 2)

    if voluntary_changes == 0:
        facing = "none"
    elif level_is_all_in:
        facing = "allin"
    elif voluntary_changes > 1:
        facing = "raise"
    else:
        facing = "bet"

    prev_pot, prev_stacks, prev_board = rh.state_at(step_index - 1)
    hero_stack = prev_stacks.get(rh.hero)
    board = prev_board.split() if prev_board else []
    hero_cards = rh.hero_cards.split()

    villain_stack = None
    if len(active) == 2:
        others = active - {rh.hero}
        if others:
            villain_stack = prev_stacks.get(next(iter(others)))

    opponents: list[EquityOpponent] | None = None
    if facing != "none":
        if opponents_override is not None:
            opponents = opponents_override
        else:
            opponents = []
            for player in sorted(active - {rh.hero}):
                shown = rh.shown_cards.get(player)
                if shown:
                    opponents.append(EquityOpponent(player_id=player, cards=shown.split()))
                else:
                    opponents.append(EquityOpponent(player_id=player))  # "qualquer duas cartas"

    # `pot_before_bet`/`bet_size` reconstruídos pra bater exatamente com o
    # pote real (`prev_pot`) e o nível que o hero precisa igualar (`level`)
    # — ver docstring do módulo. `bet_size` aqui é "o nível que precisa ser
    # igualado", não necessariamente a última aposta de um único jogador
    # (numa rua com raise, é o valor do raise; isso é o que importa pra
    # pot odds, não quem especificamente colocou cada parte).
    bet_size = level if facing != "none" else 0.0
    pot_before_bet = prev_pot - bet_size

    return context.analyze_decision(
        street=street,
        facing=facing,
        num_players_in_hand=num_players_in_hand,
        hero_cards=hero_cards,
        board=board,
        effective_bb=(hero_stack / rh.bb) if (rh.bb and hero_stack is not None) else None,
        pot_bb=(pot_before_bet / rh.bb) if rh.bb else None,
        opponents=opponents,
        pot_before_bet=float(pot_before_bet),
        bet_size=float(bet_size),
        hero_already_in=float(hero_in),
        additional_money_in=0.0,
        hero_stack=float(hero_stack) if hero_stack is not None else None,
        villain_stack=float(villain_stack) if villain_stack is not None else None,
        equity_simulation_method=equity_simulation_method,
        equity_iterations=equity_iterations,
        equity_seed=equity_seed,
    )
