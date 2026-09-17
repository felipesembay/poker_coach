"""Testes de poker_coach/decision_stats.py contra o Postgres de teste —
mesmo padrão de tests/test_bankroll.py (dados sintéticos inseridos direto
via db.save_decision_analysis, não fixtures de hand history)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm
from poker_coach import decision_stats

TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"
SITE = "testsite"


def _reset(conn):
    conn.execute("DELETE FROM decision_analysis")
    conn.commit()


def _save(conn, hand_id, step_order, **overrides):
    defaults = dict(
        site=SITE, hand_id=hand_id, step_order=step_order, tournament_id="T1",
        player="Hero", street="preflop", position="BTN", hero_cards="As Ks",
        board=None, pot_before_action_bb=None, bet_faced_bb=None, call_cost_bb=None,
        effective_stack_bb=None, number_of_opponents=None, context_type="preflop_open",
        model_type="pushfold_nash", hero_equity=None, required_equity=None,
        pot_odds_ratio=None, ev_call_bb=None, ev_fold_bb=0.0, ev_push_bb=None,
        recommended_action=None, actual_action=None, actual_result_bb=None,
        assumptions=["teste"],
    )
    defaults.update(overrides)
    dbm.save_decision_analysis(conn, **defaults)
    conn.commit()


def test_preflop_model_performance_empty():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    result = decision_stats.preflop_model_performance(conn)
    assert result == {
        "n": 0, "avg_ev_theoretical_bb": None, "avg_actual_result_bb": None,
        "error_rate_pct": None, "avg_ev_lost_on_error_bb": None,
    }


def test_preflop_model_performance_aggregates_and_flags_errors():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    # Correta: modelo manda push, hero deu push.
    _save(conn, "h1", 1, ev_push_bb=2.0, recommended_action="push",
          actual_action="allin", actual_result_bb=5.0)
    # Erro: modelo manda fold (EV negativo), hero deu push (perdeu esse EV).
    _save(conn, "h2", 1, ev_push_bb=-1.5, recommended_action="fold",
          actual_action="allin", actual_result_bb=-3.0)
    # Correta: modelo manda fold, hero foldou.
    _save(conn, "h3", 1, ev_push_bb=-0.8, recommended_action="fold",
          actual_action="fold", actual_result_bb=0.0)

    result = decision_stats.preflop_model_performance(conn)
    assert result["n"] == 3
    assert result["avg_ev_theoretical_bb"] == round((2.0 - 1.5 - 0.8) / 3, 3)
    assert result["avg_actual_result_bb"] == round((5.0 - 3.0 + 0.0) / 3, 3)
    assert result["error_rate_pct"] == round(1 / 3 * 100, 1)
    assert result["avg_ev_lost_on_error_bb"] == 1.5


def test_contextual_decision_performance_aggregates_and_flags_errors():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    _save(conn, "h4", 1, model_type="contextual_ev", street="river",
          hero_equity=0.7, required_equity=0.25, ev_call_bb=3.0, ev_fold_bb=0.0,
          ev_push_bb=None, recommended_action="call", actual_action="call",
          actual_result_bb=4.0)
    _save(conn, "h5", 1, model_type="contextual_ev", street="river",
          hero_equity=0.1, required_equity=0.30, ev_call_bb=-2.0, ev_fold_bb=0.0,
          ev_push_bb=None, recommended_action="fold", actual_action="call",
          actual_result_bb=-2.0)

    result = decision_stats.contextual_decision_performance(conn)
    assert result["n"] == 2
    assert result["avg_hero_equity_pct"] == round((0.7 + 0.1) / 2 * 100, 1)
    assert result["avg_required_equity_pct"] == round((0.25 + 0.30) / 2 * 100, 1)
    assert result["avg_ev_call_bb"] == round((3.0 - 2.0) / 2, 3)
    assert result["error_rate_pct"] == 50.0
    assert result["avg_actual_result_bb"] == 1.0


def test_postflop_performance_breaks_down_by_street_position_stack_and_texture():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    _save(conn, "h6", 1, model_type="contextual_ev", street="flop", position="BTN",
          board="2c 7d 9h", effective_stack_bb=25.0, hero_equity=0.6,
          ev_call_bb=1.0, required_equity=0.3, actual_result_bb=2.0)
    _save(conn, "h7", 1, model_type="postflop_check_only", street="flop", position="BB",
          board="5s 5h Kc", effective_stack_bb=8.0, hero_equity=None,
          ev_call_bb=None, required_equity=None, actual_result_bb=-1.0,
          recommended_action="check", actual_action="check")

    result = decision_stats.postflop_performance(conn)

    flop = next(s for s in result["by_street"] if s["street"] == "flop")
    assert flop["n"] == 2
    assert flop["avg_hero_equity_pct"] == 60.0  # só h6 tem hero_equity não-nulo
    assert flop["avg_actual_result_bb"] == round((2.0 - 1.0) / 2, 3)

    turn = next(s for s in result["by_street"] if s["street"] == "turn")
    assert turn["n"] == 0

    btn = next(p for p in result["by_position"] if p["position"] == "BTN")
    assert btn["n"] == 1
    bb_pos = next(p for p in result["by_position"] if p["position"] == "BB")
    assert bb_pos["n"] == 1

    bucket_20_30 = next(b for b in result["by_stack"] if b["bucket"] == "20-30BB")
    assert bucket_20_30["n"] == 1
    bucket_5_10 = next(b for b in result["by_stack"] if b["bucket"] == "5-10BB")
    assert bucket_5_10["n"] == 1

    rainbow = next(t for t in result["by_texture"] if t["texture"] == "unpaired-rainbow")
    assert rainbow["n"] == 1
    paired = next(t for t in result["by_texture"] if t["texture"] == "paired-rainbow")
    assert paired["n"] == 1


def test_save_decision_analysis_upserts_same_step_instead_of_duplicating():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    _save(conn, "h8", 1, ev_push_bb=1.0)
    _save(conn, "h8", 1, ev_push_bb=9.0)  # mesmo (site, hand_id, step_order)
    rows = conn.execute(
        "SELECT ev_push_bb FROM decision_analysis WHERE site=? AND hand_id=?", (SITE, "h8")
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 9.0
