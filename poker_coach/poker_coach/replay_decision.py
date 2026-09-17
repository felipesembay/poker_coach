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

    prev_pot, prev_stacks, _prev_board = rh.state_at(step_index - 1)
    hero_stack = prev_stacks.get(rh.hero)
    # Board vem do passo ATUAL, não do anterior: ele é revelado por
    # inteiro pra rua toda antes de qualquer ação (diferente de
    # pot/stacks, que só refletem o que já foi apostado). Usar o passo
    # anterior quebra exatamente na PRIMEIRA ação de cada rua nova (ele
    # ainda carrega o board da rua ANTERIOR — ex.: primeira ação do flop
    # herdaria board vazio do fim do preflop).
    board = step.board_so_far.split() if step.board_so_far else []
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


def build_decision_analysis_record(
    rh: ReplayHand,
    step_index: int,
    analysis: context.DecisionAnalysis,
    *,
    actual_result_bb: float | None = None,
) -> dict:
    """Monta os campos pra `db.save_decision_analysis(conn, **record)` a
    partir de uma análise já calculada (`analyze_hero_step`). Não toca no
    banco — quem chama passa `actual_result_bb` (resultado da mão inteira
    em BB, vindo de `hands.hero_net_chips`, uma leitura que só o chamador
    tem o `conn` pra fazer) e faz o `save_decision_analysis` de verdade.

    `actual_result_bb` é o resultado da MÃO INTEIRA, não desta decisão
    isolada (não existe contrafactual — não sabemos o que teria acontecido
    se o hero tivesse escolhido outra ação). Isso é uma limitação
    documentada, não escondida: ver `assumptions` no registro salvo.
    """
    step = rh.steps[step_index]
    bb = rh.bb or None
    _, prev_stacks, _ = rh.state_at(step_index - 1)
    hero_stack_chips = prev_stacks.get(rh.hero)
    ctx = analysis.context

    common = dict(
        site=rh.site, hand_id=rh.hand_id, step_order=step.order,
        tournament_id=rh.tournament_id, player=rh.hero, street=step.street,
        position=rh.positions.get(rh.hero), hero_cards=rh.hero_cards,
        # Board do passo ATUAL, não do anterior — ver analyze_hero_step.
        board=step.board_so_far or None, context_type=ctx.context_type,
        model_type=ctx.recommended_model, actual_action=step.action,
        actual_result_bb=actual_result_bb,
    )

    if analysis.nash is not None:
        n = analysis.nash
        return {
            **common,
            "pot_before_action_bb": n.pot_bb,
            "bet_faced_bb": None,
            "call_cost_bb": None,
            "effective_stack_bb": n.effective_bb,
            "number_of_opponents": None,
            "hero_equity": n.equity_vs_call_range,
            "required_equity": None,
            "pot_odds_ratio": None,
            "ev_call_bb": None,
            "ev_fold_bb": 0.0,
            "ev_push_bb": n.ev_push_bb,
            "recommended_action": n.recommendation,
            "assumptions": ctx.reasoning,
        }

    c = analysis.contextual
    assert c is not None  # analyze_hero_step sempre retorna nash XOR contextual
    by_action = {d.action: d for d in c.decisions}
    best = c.best()
    po = c.pot_odds
    eqr = c.equity
    return {
        **common,
        "pot_before_action_bb": (po.pot_before_bet / bb) if (po and bb) else None,
        "bet_faced_bb": (po.villain_bet / bb) if (po and bb) else None,
        "call_cost_bb": (po.hero_call_cost / bb) if (po and bb) else None,
        "effective_stack_bb": (hero_stack_chips / bb) if (hero_stack_chips is not None and bb) else None,
        "number_of_opponents": eqr.num_opponents if eqr else None,
        "hero_equity": eqr.hero_equity if eqr else None,
        "required_equity": po.required_equity if po else None,
        "pot_odds_ratio": po.pot_odds_ratio if po else None,
        "ev_call_bb": (by_action["call"].ev / bb) if (bb and by_action.get("call") and by_action["call"].applicable and by_action["call"].ev is not None) else None,
        "ev_fold_bb": (by_action["fold"].ev / bb) if (bb and by_action.get("fold") and by_action["fold"].applicable and by_action["fold"].ev is not None) else None,
        "ev_push_bb": (by_action["push"].ev / bb) if (bb and by_action.get("push") and by_action["push"].applicable and by_action["push"].ev is not None) else None,
        "recommended_action": best.action if best else None,
        "assumptions": [*ctx.reasoning, *c.assumptions],
    }
