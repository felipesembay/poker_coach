import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.equity_engine import EquityOpponent
from poker_coach.ev_engine import EVInputError, evaluate_decision

# Board/mãos fixas reaproveitadas do test_equity_engine.py: river completo,
# vitória/derrota exatas (sem incerteza), pra isolar a matemática do EV.
WIN_BOARD = ["2c", "7d", "Jh", "4s", "6c"]


def test_check_when_not_facing_bet():
    result = evaluate_decision(
        facing_bet=False,
        street="flop",
        hero_cards=["As", "Ks"],
        board=["2c", "7d", "9h"],
    )
    by_action = {d.action: d for d in result.decisions}
    assert by_action["check"].applicable is True
    assert by_action["check"].ev == 0.0
    assert by_action["fold"].applicable is False
    assert by_action["call"].applicable is False
    assert by_action["push"].applicable is False
    assert result.equity is None
    assert result.pot_odds is None


def test_call_ev_positive_when_hero_wins_exact():
    result = evaluate_decision(
        facing_bet=True,
        street="river",
        hero_cards=["Qs", "Qh"],
        board=WIN_BOARD,
        opponents=[EquityOpponent(player_id="v1", cards=["9d", "9c"])],
        pot_before_bet=10.0,
        bet_size=5.0,
    )
    by_action = {d.action: d for d in result.decisions}
    assert result.equity.hero_equity == 1.0
    assert result.pot_odds.pot_after_call == 20.0
    assert by_action["call"].ev == pytest.approx(1.0 * 20.0 - 5.0)
    assert by_action["fold"].ev == 0.0
    assert result.best().action == "call"


def test_call_ev_negative_when_hero_loses_exact():
    result = evaluate_decision(
        facing_bet=True,
        street="river",
        hero_cards=["9d", "9c"],
        board=WIN_BOARD,
        opponents=[EquityOpponent(player_id="v1", cards=["Qs", "Qh"])],
        pot_before_bet=10.0,
        bet_size=5.0,
    )
    by_action = {d.action: d for d in result.decisions}
    assert result.equity.hero_equity == 0.0
    assert by_action["call"].ev == pytest.approx(0.0 * 20.0 - 5.0)
    # fold (EV=0) bate call (EV=-5) — a melhor decisão aplicável é fold.
    assert result.best().action == "fold"


def test_push_ev_heads_up_with_villain_stack():
    result = evaluate_decision(
        facing_bet=True,
        street="river",
        hero_cards=["Qs", "Qh"],
        board=WIN_BOARD,
        opponents=[EquityOpponent(player_id="v1", cards=["9d", "9c"])],
        pot_before_bet=10.0,
        bet_size=5.0,
        hero_stack=30.0,
        villain_stack=40.0,
    )
    by_action = {d.action: d for d in result.decisions}
    assert by_action["push"].applicable is True
    # eff = min(30,40) = 30; dead_pot = 10+5+0 = 15
    # ev = 1.0 * (15 + 2*30) - 30 = 75 - 30 = 45
    assert by_action["push"].ev == pytest.approx(45.0)
    assert "sempre paga" in by_action["push"].note or "fold equity" in by_action["push"].note


def test_push_not_applicable_without_villain_stack():
    result = evaluate_decision(
        facing_bet=True,
        street="river",
        hero_cards=["Qs", "Qh"],
        board=WIN_BOARD,
        opponents=[EquityOpponent(player_id="v1", cards=["9d", "9c"])],
        pot_before_bet=10.0,
        bet_size=5.0,
        hero_stack=30.0,
    )
    by_action = {d.action: d for d in result.decisions}
    assert by_action["push"].applicable is False
    assert by_action["push"].ev is None


def test_push_not_applicable_multiway():
    result = evaluate_decision(
        facing_bet=True,
        street="flop",
        hero_cards=["Ah", "Ad"],
        board=["2c", "7d", "9h"],
        opponents=[
            EquityOpponent(player_id="v1"),
            EquityOpponent(player_id="v2"),
        ],
        pot_before_bet=10.0,
        bet_size=5.0,
        hero_stack=30.0,
        villain_stack=40.0,
        equity_iterations=1000,
        equity_seed=1,
    )
    by_action = {d.action: d for d in result.decisions}
    assert by_action["push"].applicable is False
    assert "Multiway" in by_action["push"].note


def test_push_not_applicable_when_stack_not_bigger_than_call():
    result = evaluate_decision(
        facing_bet=True,
        street="river",
        hero_cards=["Qs", "Qh"],
        board=WIN_BOARD,
        opponents=[EquityOpponent(player_id="v1", cards=["9d", "9c"])],
        pot_before_bet=10.0,
        bet_size=5.0,
        hero_stack=5.0,  # cobre só o call, não dá pra empurrar mais
        villain_stack=40.0,
    )
    by_action = {d.action: d for d in result.decisions}
    assert by_action["push"].applicable is False


def test_requires_opponents_when_facing_bet():
    with pytest.raises(EVInputError, match="opponents"):
        evaluate_decision(
            facing_bet=True,
            street="river",
            hero_cards=["Qs", "Qh"],
            board=WIN_BOARD,
            pot_before_bet=10.0,
            bet_size=5.0,
        )
