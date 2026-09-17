import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.context import ContextInputError, analyze_decision, classify_context
from poker_coach.equity_engine import EquityOpponent
from poker_coach.ev_engine import EVInputError

WIN_BOARD = ["2c", "7d", "Jh", "4s", "6c"]


# ---------------- classify_context: os 5 contextos da seção 9 ----------------

def test_context_1_preflop_open_first_to_act():
    ctx = classify_context(street="preflop", facing="none", num_players_in_hand=2)
    assert ctx.context_type == "preflop_open"
    assert ctx.recommended_model == "pushfold_nash"


def test_context_2_preflop_facing_raise_heads_up():
    ctx = classify_context(street="preflop", facing="raise", num_players_in_hand=2)
    assert ctx.context_type == "preflop_facing_raise"
    assert ctx.recommended_model == "contextual_ev"


def test_context_3_preflop_facing_allin_multiway():
    ctx = classify_context(street="preflop", facing="allin", num_players_in_hand=3)
    assert ctx.context_type == "preflop_multiway_facing_allin"
    assert ctx.recommended_model == "contextual_ev"
    assert any("multiway" in r.lower() or "jogadores" in r.lower() for r in ctx.reasoning)


def test_context_4_flop_facing_bet():
    ctx = classify_context(street="flop", facing="bet", num_players_in_hand=2)
    assert ctx.context_type == "flop_facing_bet"
    assert ctx.recommended_model == "contextual_ev"


def test_context_5_flop_first_to_act_no_bet():
    ctx = classify_context(street="flop", facing="none", num_players_in_hand=2)
    assert ctx.context_type == "postflop_first_to_act"
    assert ctx.recommended_model == "postflop_check_only"


def test_rejects_invalid_street():
    with pytest.raises(ContextInputError, match="street"):
        classify_context(street="bogus", facing="none", num_players_in_hand=2)


def test_rejects_invalid_facing():
    with pytest.raises(ContextInputError, match="facing"):
        classify_context(street="flop", facing="bogus", num_players_in_hand=2)


def test_rejects_too_few_players():
    with pytest.raises(ContextInputError, match="num_players_in_hand"):
        classify_context(street="flop", facing="none", num_players_in_hand=1)


# ---------------- analyze_decision: dispatcher ----------------

def test_analyze_dispatches_to_pushfold_nash_for_preflop_open():
    result = analyze_decision(
        street="preflop",
        facing="none",
        num_players_in_hand=2,
        hero_cards=["As", "Ks"],
        effective_bb=10.0,
        pot_bb=1.5,
    )
    assert result.context.recommended_model == "pushfold_nash"
    assert result.contextual is None
    assert result.nash is not None
    assert result.nash.recommendation in ("push", "fold")
    assert result.nash.effective_bb == 10.0
    assert result.nash.pot_bb == 1.5
    # AKs 10bb efetivo é um push clássico de livro-texto.
    assert result.nash.recommendation == "push"


def test_analyze_pushfold_nash_requires_effective_bb_and_pot_bb():
    with pytest.raises(ContextInputError, match="effective_bb"):
        analyze_decision(
            street="preflop",
            facing="none",
            num_players_in_hand=2,
            hero_cards=["As", "Ks"],
        )


def test_analyze_dispatches_to_contextual_ev_for_postflop_facing_bet():
    result = analyze_decision(
        street="river",
        facing="bet",
        num_players_in_hand=2,
        hero_cards=["Qs", "Qh"],
        board=WIN_BOARD,
        opponents=[EquityOpponent(player_id="v1", cards=["9d", "9c"])],
        pot_before_bet=10.0,
        bet_size=5.0,
    )
    assert result.context.recommended_model == "contextual_ev"
    assert result.nash is None
    assert result.contextual is not None
    by_action = {d.action: d for d in result.contextual.decisions}
    assert by_action["call"].ev == pytest.approx(1.0 * 20.0 - 5.0)


def test_analyze_dispatches_to_check_only_for_postflop_first_to_act():
    result = analyze_decision(
        street="flop",
        facing="none",
        num_players_in_hand=2,
        hero_cards=["As", "Ks"],
        board=["2c", "7d", "9h"],
    )
    assert result.context.recommended_model == "postflop_check_only"
    assert result.nash is None
    by_action = {d.action: d for d in result.contextual.decisions}
    assert by_action["check"].ev == 0.0


def test_analyze_contextual_ev_still_requires_opponents():
    with pytest.raises(EVInputError, match="opponents"):
        analyze_decision(
            street="river",
            facing="bet",
            num_players_in_hand=2,
            hero_cards=["Qs", "Qh"],
            board=WIN_BOARD,
            pot_before_bet=10.0,
            bet_size=5.0,
        )
