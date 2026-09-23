import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.models import Seat
from poker_coach.replay import ReplayHand, ReplayStep
from poker_coach.rl.export import (
    HandOutcome,
    build_rl_row,
    hero_decision_steps,
    normalize_action_class,
    resolve_actual_engine_action,
    temporal_split,
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


# --- resolve_actual_engine_action / normalize_action_class ---

def test_resolve_actual_engine_action_all_in_is_push():
    assert resolve_actual_engine_action("bet", True) == "push"
    assert resolve_actual_engine_action("raise", True) == "push"
    assert resolve_actual_engine_action("allin", True) == "push"


def test_resolve_actual_engine_action_modeled_non_allin():
    assert resolve_actual_engine_action("fold", False) == "fold"
    assert resolve_actual_engine_action("call", False) == "call"
    assert resolve_actual_engine_action("check", False) == "check"


def test_resolve_actual_engine_action_unmodeled_bet_raise_is_none():
    # Motor atual não modela sizing de bet/raise do hero sem ir all-in —
    # não pode inventar EV pra essa ação.
    assert resolve_actual_engine_action("bet", False) is None
    assert resolve_actual_engine_action("raise", False) is None


def test_normalize_action_class_preserves_bet_raise_when_not_all_in():
    assert normalize_action_class("bet", False) == "bet"
    assert normalize_action_class("raise", False) == "raise"
    assert normalize_action_class("raise", True) == "push"


# --- hero_decision_steps ---

def test_hero_decision_steps_skips_non_decision_actions():
    rh = _base_hand()
    rh.steps = [
        ReplayStep(1, "preflop", "hero", "SB", "post_sb", 1, False, 1, {}, ""),
        ReplayStep(2, "preflop", "villain", "BB", "post_bb", 2, False, 3, {}, ""),
        ReplayStep(3, "preflop", "hero", "SB", "raise", 8, False, 11, {"hero": 91, "villain": 98}, ""),
        ReplayStep(4, "preflop", "villain", "BB", "fold", 0, False, 11, {}, ""),
    ]
    rh.street_first_index = {"preflop": 0}
    assert hero_decision_steps(rh) == [2]


def test_hero_decision_steps_empty_without_hero():
    rh = _base_hand(hero=None)
    rh.steps = [ReplayStep(1, "preflop", "hero", "SB", "raise", 8, False, 8, {}, "")]
    assert hero_decision_steps(rh) == []


# --- build_rl_row: reference available (preflop open -> nash) ---

def test_build_rl_row_preflop_open_has_nash_reference_and_ev_gap():
    rh = _base_hand()
    rh.steps = [
        ReplayStep(1, "preflop", "hero", "SB", "post_sb", 1, False, 1,
                   {"hero": 99, "villain": 100}, ""),
        ReplayStep(2, "preflop", "villain", "BB", "post_bb", 2, False, 3,
                   {"hero": 99, "villain": 98}, ""),
        ReplayStep(3, "preflop", "hero", "SB", "raise", 8, True, 11,
                   {"hero": 91, "villain": 98}, ""),
    ]
    rh.street_first_index = {"preflop": 0}
    outcome = HandOutcome(actual_result_bb=4.5, showdown=False, finish_position=None, eliminated=False)

    row = build_rl_row(rh, 2, outcome)

    assert row["reference_source"] == "nash"
    assert row["context_type"] == "preflop_open"
    assert row["action_class"] == "push"  # all_in=True colapsa pra push
    assert row["actual_result_bb"] == 4.5  # OUTCOME preservado
    assert row["ev_best"] is not None
    if row["reference_action"] == "push":
        assert row["ev_actual"] == pytest.approx(row["ev_best"])
        assert row["ev_gap"] == pytest.approx(0.0)
    else:
        # hero empurrou mas Nash mandaria foldar: ev_actual é o EV do push
        # (ação real dele), não o do fold recomendado.
        assert row["ev_gap"] is not None and row["ev_gap"] >= 0
    history = json.loads(row["action_history"])
    assert history[0]["action"] == "post_sb"
    assert history[1]["action"] == "post_bb"


def test_build_rl_row_bare_raise_not_all_in_has_no_ev_actual():
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
    outcome = HandOutcome(actual_result_bb=0.0, showdown=False, finish_position=None, eliminated=False)

    row = build_rl_row(rh, 2, outcome)

    # Nash isolado só conhece push/fold — um raise que não foi all-in não
    # é nenhum dos dois, então não inventamos EV pra ele.
    assert row["ev_actual"] is None
    assert row["ev_gap"] is None
    assert row["reference_action"] in ("push", "fold")  # referência continua disponível


def test_build_rl_row_facing_bet_uses_ev_engine_reference():
    rh = _base_hand()
    rh.steps = [
        ReplayStep(10, "river", "villain", "BB", "bet", 5, False, 15,
                   {"hero": 80, "villain": 75}, WIN_BOARD),
        ReplayStep(11, "river", "hero", "SB", "call", 5, False, 20,
                   {"hero": 75, "villain": 75}, WIN_BOARD),
    ]
    rh.street_first_index = {"preflop": -5, "river": 0}
    outcome = HandOutcome(actual_result_bb=-2.5, showdown=True, finish_position=3, eliminated=False)

    row = build_rl_row(rh, 1, outcome)

    assert row["reference_source"] == "ev_engine"
    assert row["showdown"] is True
    assert row["finish_position"] == 3
    assert row["ev_actual"] is not None  # "call" é modelado
    assert row["ev_best"] is not None
    assert row["ev_gap"] == pytest.approx(row["ev_best"] - row["ev_actual"])


def test_build_rl_row_ev_engine_values_are_bb_not_chips():
    """Regressão: `DecisionEV.ev` do ev_engine vem em FICHAS CRUAS (os
    inputs que `context.analyze_decision` repassa pra ele são fichas, não
    BB) — só o branch Nash já vem em BB. Um bug real chegou a expor
    ev_gap na casa de MILHARES de "BB" (fichas cruas sem dividir) numa
    mão real com bb=600. Replica a mesma ordem de grandeza aqui."""
    turn_board = "2c 7d Jh 4s"
    rh = _base_hand(bb=600, sb=300)
    rh.steps = [
        ReplayStep(10, "turn", "villain", "BB", "bet", 950, False, 3800,
                   {"hero": 50695, "villain": 49745}, turn_board),
        ReplayStep(11, "turn", "hero", "SB", "call", 950, False, 4750,
                   {"hero": 49745, "villain": 49745}, turn_board),
    ]
    rh.street_first_index = {"preflop": -5, "turn": 0}
    outcome = HandOutcome(actual_result_bb=0.0, showdown=False, finish_position=None, eliminated=False)

    row = build_rl_row(rh, 1, outcome)

    assert row["reference_source"] == "ev_engine"
    assert row["ev_actual"] is not None
    # Chips crus estariam na casa de DEZENAS DE MILHARES (stack ~50000
    # fichas) — em BB (/600), até o EV de push tem que ficar limitado a
    # poucas vezes o stack efetivo em BB (~83 aqui), nunca a mesma ordem
    # de grandeza das fichas cruas (o bug real chegou a 8806 "BB").
    bound = 3 * row["effective_stack_bb"]
    assert abs(row["ev_actual"]) < bound
    assert abs(row["ev_best"]) < bound
    assert row["ev_gap"] < bound


def test_build_rl_row_reference_unavailable_keeps_behavior_fields():
    rh = _base_hand(hero_cards="Zz Zz")  # carta inválida de propósito
    rh.steps = [
        ReplayStep(10, "river", "villain", "BB", "bet", 5, False, 15,
                   {"hero": 80, "villain": 75}, WIN_BOARD),
        ReplayStep(11, "river", "hero", "SB", "call", 5, False, 20,
                   {"hero": 75, "villain": 75}, WIN_BOARD),
    ]
    rh.street_first_index = {"preflop": -5, "river": 0}
    outcome = HandOutcome(actual_result_bb=-2.5, showdown=False, finish_position=None, eliminated=False)

    row = build_rl_row(rh, 1, outcome)

    assert row["reference_source"] == "unavailable"
    assert row["reference_action"] is None
    assert row["ev_gap"] is None
    # BEHAVIOR/OUTCOME continuam presentes mesmo sem referência.
    assert row["action_taken"] == "call"
    assert row["actual_result_bb"] == -2.5


# --- temporal_split ---

def test_temporal_split_orders_by_ts_and_does_not_leak_hands():
    import pandas as pd

    rows = []
    for day in range(1, 11):
        for step in (1, 2):
            rows.append({
                "site": "s", "hand_id": f"h{day}", "ts": f"2026-01-{day:02d}T00:00:00",
                "step_order": step,
            })
    df = pd.DataFrame(rows)

    train, val, test = temporal_split(df, train=0.7, val=0.15, test=0.15)

    train_hands = set(train["hand_id"])
    val_hands = set(val["hand_id"])
    test_hands = set(test["hand_id"])
    assert not (train_hands & val_hands)
    assert not (val_hands & test_hands)
    assert not (train_hands & test_hands)
    assert len(train) + len(val) + len(test) == len(df)
    assert train["ts"].max() <= val["ts"].min()
    assert val["ts"].max() <= test["ts"].min()
