"""Testes de poker_coach/rl/audit.py contra o Postgres de teste, mesmo
padrão de test_pushfold.py::test_analyze_scope_skips_limped_pot (fixture
real do PartyPoker, não hand history sintético)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm
from poker_coach.parsers import partypoker
from poker_coach.rl import audit as rl_audit

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"


def _load_fixture(conn):
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())
    for t in ["actions", "seats", "showdowns", "results", "hands", "tournaments"]:
        conn.execute(f"DELETE FROM {t}")
    for h in hands:
        dbm.insert_hand(conn, h)
    conn.commit()
    return hands


def test_run_audit_counts_match_fixture_hands():
    conn = dbm.connect(TEST_DSN)
    hands = _load_fixture(conn)

    report = rl_audit.run_audit(conn, site="partypoker")

    assert report.hands_total == len(hands)
    assert report.hands_ok + report.hands_discarded_no_hero + report.hands_error == report.hands_total
    # Ambas as mãos do fixture têm hero com cartas conhecidas.
    assert report.hands_ok == len(hands)
    assert report.decisions_total > 0
    assert sum(report.decisions_by_street.values()) == report.decisions_total
    assert (report.decisions_reference_available
            + report.decisions_reference_unavailable) == report.decisions_total


def test_format_report_includes_key_sections():
    conn = dbm.connect(TEST_DSN)
    _load_fixture(conn)
    report = rl_audit.run_audit(conn, site="partypoker")
    text = rl_audit.format_report(report)
    assert "Dataset Audit" in text
    assert "Hero decision points" in text
    assert "Distribuição por street" in text
    assert "Qualidade de referência" in text


def test_run_audit_empty_site_has_zero_hands():
    conn = dbm.connect(TEST_DSN)
    _load_fixture(conn)
    report = rl_audit.run_audit(conn, site="nao_existe")
    assert report.hands_total == 0
    assert report.decisions_total == 0
