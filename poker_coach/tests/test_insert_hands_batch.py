"""Testes de poker_coach/db.py::insert_hands_batch — tem que produzir
exatamente o mesmo estado final de N chamadas a insert_hand (mesmo
fixture real do PartyPoker usado em test_pushfold.py), só em lote."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm
from poker_coach.parsers import partypoker

TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"
ROOT = pathlib.Path(__file__).resolve().parents[1]


def _reset(conn):
    for t in ["actions", "seats", "showdowns", "results", "hands", "tournaments"]:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


def _counts(conn):
    return {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ["hands", "actions", "seats", "showdowns", "results", "tournaments"]
    }


def test_insert_hands_batch_matches_per_hand_insert():
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())

    conn_a = dbm.connect(TEST_DSN)
    _reset(conn_a)
    for h in hands:
        dbm.insert_hand(conn_a, h)
    conn_a.commit()
    per_hand_counts = _counts(conn_a)

    conn_b = dbm.connect(TEST_DSN)
    _reset(conn_b)
    new = dbm.insert_hands_batch(conn_b, hands)
    conn_b.commit()
    batch_counts = _counts(conn_b)

    assert new == len(hands)
    assert batch_counts == per_hand_counts


def test_insert_hands_batch_is_idempotent_on_reimport():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())

    first = dbm.insert_hands_batch(conn, hands)
    conn.commit()
    counts_after_first = _counts(conn)

    second = dbm.insert_hands_batch(conn, hands)
    conn.commit()
    counts_after_second = _counts(conn)

    assert first == len(hands)
    assert second == 0  # reimport: nenhuma mão nova
    assert counts_after_first == counts_after_second  # nao duplicou nada


def test_insert_hands_batch_empty_list_is_noop():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    assert dbm.insert_hands_batch(conn, []) == 0
    assert _counts(conn)["hands"] == 0


def test_insert_hands_batch_partial_overlap_only_inserts_new_ones():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())

    dbm.insert_hand(conn, hands[0])
    conn.commit()

    new = dbm.insert_hands_batch(conn, hands)
    conn.commit()

    assert new == len(hands) - 1  # so a segunda mao era nova
    assert _counts(conn)["hands"] == len(hands)
