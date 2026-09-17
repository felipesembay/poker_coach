import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.equity_engine import EquityOpponent
from poker_coach.models import Seat
from poker_coach.replay import ReplayHand, ReplayStep
from poker_coach.replay_decision import (
    ReplayDecisionError,
    analyze_hero_step,
    build_decision_analysis_record,
)

WIN_BOARD = "2c 7d Jh 4s 6c"


def _base_hand(**overrides) -> ReplayHand:
    defaults = dict(
        site="test", hand_id="h1", tournament_id="t1", tournament_name="T",
        buyin=10.0, ts="2026-01-01T00:00:00", sb=1, bb=2, ante=0, button_seat=1,
        hero="hero", hero_cards="Qs Qh",
        seats=[Seat(1, "hero", 100), Seat(2, "villain", 100)],
        positions={"hero": "SB", "villain": "BB"},
        seat_order=["hero", "villain"],
        board=None, shown_cards={}, steps=[], street_first_index={},
    )
    defaults.update(overrides)
    return ReplayHand(**defaults)


def test_preflop_open_routes_to_pushfold_nash():
    rh = _base_hand()
    rh.steps = [
        ReplayStep(1, "preflop", "hero", "SB", "post_sb", 1, False, 1,
                   {"hero": 99, "villain": 100}, ""),
        ReplayStep(2, "preflop", "villain", "BB", "post_bb", 2, False, 3,
                   {"hero": 99, "villain": 98}, ""),
        ReplayStep(3, "preflop", "hero", "SB", "raise", 8, False, 11,
                   {"hero": 91, "villain": 98}, ""),
    ]
    rh.street_first_index = {"preflop": 0}

    result = analyze_hero_step(rh, 2)  # o passo do hero (índice 2), estado ANTES dele
    assert result.context.context_type == "preflop_open"
    assert result.context.recommended_model == "pushfold_nash"
    assert result.nash is not None
    assert result.nash.effective_bb == pytest.approx(99 / 2)  # stack do hero antes da ação / bb
    assert result.nash.pot_bb == pytest.approx(3 / 2)  # sb+bb / bb = dinheiro morto

    record = build_decision_analysis_record(rh, 2, result, actual_result_bb=4.5)
    assert record["model_type"] == "pushfold_nash"
    assert record["context_type"] == "preflop_open"
    assert record["effective_stack_bb"] == pytest.approx(99 / 2)
    assert record["pot_before_action_bb"] == pytest.approx(3 / 2)
    assert record["hero_equity"] == result.nash.equity_vs_call_range
    assert record["ev_push_bb"] == result.nash.ev_push_bb
    assert record["ev_fold_bb"] == 0.0
    assert record["ev_call_bb"] is None
    assert record["recommended_action"] == result.nash.recommendation
    assert record["actual_action"] == "raise"
    assert record["actual_result_bb"] == 4.5
    assert record["player"] == "hero"
    assert record["street"] == "preflop"


def test_postflop_facing_bet_matches_pot_odds_spec_example():
    rh = _base_hand()
    rh.steps = [
        ReplayStep(10, "river", "villain", "BB", "bet", 5, False, 15,
                   {"hero": 80, "villain": 75}, WIN_BOARD),
        ReplayStep(11, "river", "hero", "SB", "call", 5, False, 20,
                   {"hero": 75, "villain": 75}, WIN_BOARD),
    ]
    rh.street_first_index = {"preflop": -5, "river": 0}  # preflop irrelevante aqui

    result = analyze_hero_step(
        rh, 1,
        opponents_override=[EquityOpponent(player_id="villain", cards=["9d", "9c"])],
    )
    assert result.context.context_type == "river_facing_bet"
    assert result.context.recommended_model == "contextual_ev"
    po = result.contextual.pot_odds
    assert po.pot_before_bet == pytest.approx(10.0)
    assert po.villain_bet == pytest.approx(5.0)
    assert po.hero_call_cost == pytest.approx(5.0)
    assert po.pot_after_call == pytest.approx(20.0)
    assert po.required_equity == pytest.approx(0.25)
    assert result.contextual.equity.hero_equity == 1.0
    by_action = {d.action: d for d in result.contextual.decisions}
    assert by_action["call"].ev == pytest.approx(15.0)  # 1.0*20 - 5

    record = build_decision_analysis_record(rh, 1, result, actual_result_bb=-2.0)
    assert record["model_type"] == "contextual_ev"
    assert record["pot_before_action_bb"] == pytest.approx(5.0)  # 10 chips / bb=2
    assert record["bet_faced_bb"] == pytest.approx(2.5)  # 5 / 2
    assert record["call_cost_bb"] == pytest.approx(2.5)
    assert record["hero_equity"] == 1.0
    assert record["required_equity"] == pytest.approx(0.25)
    assert record["ev_call_bb"] == pytest.approx(7.5)  # 15 chips / bb=2
    # Hero sempre vence (equity=1.0) e ainda tem fichas sobrando pra
    # empurrar mais que o call (hero_stack=80 > call_cost=5, villão=75) —
    # push maximiza o que entra no pote, então bate o call em EV.
    assert record["recommended_action"] == "push"
    assert record["actual_action"] == "call"
    assert record["actual_result_bb"] == -2.0
    assert record["number_of_opponents"] == 1


def test_facing_raise_does_not_double_count_heros_own_prior_bet():
    rh = _base_hand()
    rh.steps = [
        ReplayStep(10, "river", "hero", "SB", "bet", 5, False, 15,
                   {"hero": 75, "villain": 80}, WIN_BOARD),
        ReplayStep(11, "river", "villain", "BB", "raise", 15, False, 30,
                   {"hero": 75, "villain": 65}, WIN_BOARD),
        ReplayStep(12, "river", "hero", "SB", "call", 10, False, 40,
                   {"hero": 65, "villain": 65}, WIN_BOARD),
    ]
    rh.street_first_index = {"river": 0}

    result = analyze_hero_step(
        rh, 2,
        opponents_override=[EquityOpponent(player_id="villain", cards=["9d", "9c"])],
    )
    assert result.context.context_type == "river_facing_raise"
    po = result.contextual.pot_odds
    assert po.hero_already_in == pytest.approx(5.0)
    assert po.hero_call_cost == pytest.approx(10.0)  # 15 - 5, não 15
    assert po.pot_before_bet == pytest.approx(15.0)
    assert po.pot_after_call == pytest.approx(40.0)
    assert po.required_equity == pytest.approx(0.25)
    by_action = {d.action: d for d in result.contextual.decisions}
    assert by_action["call"].ev == pytest.approx(30.0)  # 1.0*40 - 10


def test_rejects_step_that_is_not_heros_action():
    rh = _base_hand()
    rh.steps = [
        ReplayStep(1, "river", "villain", "BB", "bet", 5, False, 15,
                   {"hero": 80, "villain": 75}, WIN_BOARD),
    ]
    rh.street_first_index = {"river": 0}
    with pytest.raises(ReplayDecisionError, match="não é uma ação do hero"):
        analyze_hero_step(rh, 0)


def test_rejects_non_decision_action():
    rh = _base_hand()
    rh.steps = [
        ReplayStep(1, "preflop", "hero", "SB", "post_sb", 1, False, 1,
                   {"hero": 99, "villain": 100}, ""),
    ]
    rh.street_first_index = {"preflop": 0}
    with pytest.raises(ReplayDecisionError, match="não é uma decisão"):
        analyze_hero_step(rh, 0)


def test_board_uses_current_step_not_previous_street_on_first_action_of_new_street():
    # Regressão: a última ação do preflop tem board_so_far="" (rua
    # antiga); a primeira ação do flop já vem com o board novo em
    # `replay.py` (revelado por inteiro antes de qualquer ação). Usar
    # state_at(step_index - 1) pro board pegava a rua ERRADA bem nesse
    # caso — sempre que o hero é o primeiro a agir numa rua nova.
    rh = _base_hand()
    rh.steps = [
        ReplayStep(7, "preflop", "villain", "BB", "check", 0, False, 6,
                   {"hero": 94, "villain": 94}, ""),
        ReplayStep(8, "flop", "hero", "SB", "check", 0, False, 6,
                   {"hero": 94, "villain": 94}, "2c 7d 9h"),
    ]
    rh.street_first_index = {"preflop": 0, "flop": 1}

    result = analyze_hero_step(rh, 1)
    assert result.context.context_type == "postflop_first_to_act"
    record = build_decision_analysis_record(rh, 1, result, actual_result_bb=0.0)
    assert record["board"] == "2c 7d 9h"


def test_rejects_hand_without_hero_cards():
    rh = _base_hand(hero_cards=None)
    rh.steps = [
        ReplayStep(1, "preflop", "hero", "SB", "raise", 8, False, 11,
                   {"hero": 91, "villain": 98}, ""),
    ]
    rh.street_first_index = {"preflop": 0}
    with pytest.raises(ReplayDecisionError, match="herói"):
        analyze_hero_step(rh, 0)
