"""Testes de poker_coach/rl/adaptive_trainer.py (seção 19 do plano)."""
import pathlib
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm
from poker_coach.rl import adaptive_trainer as at

TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"


def test_synthetic_situation_has_valid_hand_and_stack():
    s = at.synthetic_situation(bb_min=10, bb_max=20, seed=0)
    assert s.source == "synthetic"
    assert 10 <= s.effective_bb <= 20
    assert len(s.hero_cards.split()) == 2
    assert s.hand_class


def test_evaluate_response_rejects_invalid_action():
    s = at.synthetic_situation(seed=0)
    with pytest.raises(ValueError):
        at.evaluate_response(s, "raise")


def test_evaluate_response_zero_gap_when_matching_reference():
    # AA com stack curto: Nash SEMPRE recomenda push (mão premium).
    s = at.TrainingSituation(
        source="synthetic", site=None, hand_id=None, position=None,
        hero_cards="As Ah", hand_class="AA", effective_bb=10.0, pot_bb=1.5,
    )
    feedback = at.evaluate_response(s, "push")
    assert feedback.reference_action == "push"
    assert feedback.ev_gap_bb == 0.0
    assert feedback.ev_user_bb == feedback.ev_reference_bb


def test_evaluate_response_positive_gap_when_folding_a_clear_push():
    s = at.TrainingSituation(
        source="synthetic", site=None, hand_id=None, position=None,
        hero_cards="As Ah", hand_class="AA", effective_bb=10.0, pot_bb=1.5,
    )
    feedback = at.evaluate_response(s, "fold")
    assert feedback.reference_action == "push"
    assert feedback.ev_user_bb == 0.0
    assert feedback.ev_gap_bb > 0  # deixou EV na mesa foldando uma mão premium


def test_historical_situation_hides_actual_action_and_uses_real_row():
    df = pd.DataFrame([{
        "context_type": "preflop_open", "effective_stack_bb": 15.0,
        "pot_before_action_bb": 1.5, "hero_cards": "Ks Qs", "position": "BTN",
        "site": "partypoker", "hand_id": "h1", "action_class": "fold",
    }])
    s = at.historical_situation(df, seed=0)
    assert s.source == "historical"
    assert s.hero_cards == "Ks Qs"
    assert s.hand_class == "KQs"
    assert s.site == "partypoker" and s.hand_id == "h1"
    assert not hasattr(s, "action_class")  # a ação real não vaza pro spot


def test_historical_situation_none_when_no_preflop_open_rows():
    df = pd.DataFrame([{"context_type": "flop_facing_bet", "effective_stack_bb": 15.0,
                         "pot_before_action_bb": 1.5, "hero_cards": "Ks Qs"}])
    assert at.historical_situation(df) is None


def test_log_feedback_roundtrip_and_stats():
    conn = dbm.connect(TEST_DSN)
    conn.execute("DELETE FROM adaptive_trainer_log")
    conn.commit()

    s = at.TrainingSituation(
        source="synthetic", site=None, hand_id=None, position=None,
        hero_cards="As Ah", hand_class="AA", effective_bb=10.0, pot_bb=1.5,
    )
    feedback = at.evaluate_response(s, "push")
    at.log_feedback(conn, feedback)
    conn.commit()

    stats = dbm.adaptive_trainer_stats(conn)
    assert stats["total"] == 1
    assert stats["correct"] == 1
    assert stats["pct"] == 100.0
