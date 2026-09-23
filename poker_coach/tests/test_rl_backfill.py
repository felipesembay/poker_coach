"""Testes de poker_coach/rl/backfill_decision_analysis.py contra o
Postgres de teste (mesmo fixture real do PartyPoker usado em
test_rl_audit.py/test_pushfold.py)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm
from poker_coach.parsers import partypoker
from poker_coach.rl import backfill_decision_analysis as rl_backfill

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"


def _load_fixture(conn):
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())
    for t in ["actions", "seats", "showdowns", "results", "hands", "tournaments", "decision_analysis"]:
        conn.execute(f"DELETE FROM {t}")
    for h in hands:
        dbm.insert_hand(conn, h)
    conn.commit()
    return hands


def test_backfill_populates_decision_analysis_for_every_hero_decision():
    conn = dbm.connect(TEST_DSN)
    _load_fixture(conn)

    stats = rl_backfill.backfill(conn, site="partypoker")

    assert stats.decisions_error == 0
    assert stats.decisions_saved > 0
    n = conn.execute("SELECT COUNT(*) FROM decision_analysis").fetchone()[0]
    assert n == stats.decisions_saved


def test_backfill_is_idempotent_upsert_not_duplicate():
    conn = dbm.connect(TEST_DSN)
    _load_fixture(conn)

    first = rl_backfill.backfill(conn, site="partypoker")
    n1 = conn.execute("SELECT COUNT(*) FROM decision_analysis").fetchone()[0]

    second = rl_backfill.backfill(conn, site="partypoker")
    n2 = conn.execute("SELECT COUNT(*) FROM decision_analysis").fetchone()[0]

    assert first.decisions_saved == second.decisions_saved
    assert n1 == n2  # upsert por (site, hand_id, step_order), não duplica


def test_backfill_one_malformed_hand_does_not_abort_the_rest(monkeypatch):
    conn = dbm.connect(TEST_DSN)
    hands = _load_fixture(conn)
    good_hand_id = hands[1].hand_id

    from poker_coach import replay as replay_mod
    real_load = replay_mod.load
    broken_hand_id = hands[0].hand_id

    def _flaky_load(conn, site, hand_id):
        if hand_id == broken_hand_id:
            raise RuntimeError("mão malformada de propósito")
        return real_load(conn, site, hand_id)

    monkeypatch.setattr(replay_mod, "load", _flaky_load)

    stats = rl_backfill.backfill(conn, site="partypoker")

    assert stats.hands_error == 1
    assert stats.hands_ok == 1
    rows = conn.execute(
        "SELECT DISTINCT hand_id FROM decision_analysis WHERE site='partypoker'"
    ).fetchall()
    assert [r[0] for r in rows] == [good_hand_id]
