"""Testes de poker_coach/bankroll.py (evolução BB/buy-ins/dinheiro,
downswing, média por sessão, normalizado) contra o Postgres de teste —
mesmo padrão de tests/test_pushfold.py (dados sintéticos inseridos
direto nas tabelas, não fixtures de hand history)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import bankroll
from poker_coach import db as dbm

TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"
SITE = "testsite"


def _reset(conn):
    for t in ["actions", "seats", "showdowns", "results", "hands", "tournaments"]:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


def _insert_tournament(conn, tid, buyin, currency, first_seen, finish_position, prize):
    conn.execute(
        """INSERT INTO tournaments (site, tournament_id, buyin, currency, first_seen,
                                     last_seen, finish_position, prize)
           VALUES (?,?,?,?,?,?,?,?)""",
        (SITE, tid, buyin, currency, first_seen, first_seen, finish_position, prize),
    )


def _insert_hand(conn, hand_id, tid, ts, bb, hero_net_chips):
    conn.execute(
        """INSERT INTO hands (site, hand_id, tournament_id, ts, bb, hero_net_chips, favorite)
           VALUES (?,?,?,?,?,?,0)""",
        (SITE, hand_id, tid, ts, bb, hero_net_chips),
    )


def _setup_money_scenario(conn):
    _reset(conn)
    # T1: +20 lucro (30-10), T2: -10 lucro (0-10), T3: sem resultado -> excluído
    _insert_tournament(conn, "T1", 10, "USD", "2026-01-01T10:00:00", 1, 30)
    _insert_tournament(conn, "T2", 10, "USD", "2026-01-02T10:00:00", 5, 0)
    _insert_tournament(conn, "T3", 20, "USD", "2026-01-03T10:00:00", None, None)
    conn.commit()


def test_bankroll_series_money_excludes_unregistered_and_accumulates():
    conn = dbm.connect(TEST_DSN)
    _setup_money_scenario(conn)
    series = bankroll.bankroll_series(conn, unit="money")
    assert [r["period"] for r in series] == ["2026-01-01", "2026-01-02"]
    assert series[0]["value"] == 20.0 and series[0]["cumulative"] == 20.0
    assert series[1]["value"] == -10.0 and series[1]["cumulative"] == 10.0


def test_bankroll_series_buyins_self_normalizes_per_tournament():
    conn = dbm.connect(TEST_DSN)
    _setup_money_scenario(conn)
    series = bankroll.bankroll_series(conn, unit="buyins")
    # T1: (30-10)/10 = 2.0 ; T2: (0-10)/10 = -1.0
    assert series[0]["value"] == 2.0
    assert series[1]["value"] == -1.0
    assert series[1]["cumulative"] == 1.0


def test_downswing_finds_peak_to_trough():
    conn = dbm.connect(TEST_DSN)
    _setup_money_scenario(conn)
    d = bankroll.downswing(conn, unit="money")
    assert d["value"] == 10.0
    assert d["start"] == "2026-01-01"
    assert d["trough"] == "2026-01-02"
    assert d["recovery"] is None  # sem dado depois do vale que recupere o pico


def test_downswing_none_below_two_points():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    _insert_tournament(conn, "T1", 10, "USD", "2026-01-01T10:00:00", 1, 30)
    conn.commit()
    assert bankroll.downswing(conn, unit="money") is None


def test_session_average_excludes_sessions_without_result_not_zero():
    conn = dbm.connect(TEST_DSN)
    _setup_money_scenario(conn)
    avg = bankroll.session_average(conn, unit="money")
    # média só de T1/T2: (20 + -10) / 2 = 5.0 -- T3 (sem resultado) não conta como 0
    assert avg["avg"] == 5.0
    assert avg["n_sessions"] == 2
    assert avg["n_excluded"] == 1  # dia de T3 tem sessão mas sem resultado


def test_session_average_bb_includes_every_session():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    _insert_tournament(conn, "T1", 10, "USD", "2026-01-01T10:00:00", None, None)
    _insert_hand(conn, "H1", "T1", "2026-01-01T10:00:00", 100, 150)
    _insert_hand(conn, "H2", "T1", "2026-01-01T10:05:00", 100, -50)
    conn.commit()
    avg = bankroll.session_average(conn, unit="bb")
    assert avg["n_excluded"] == 0
    assert avg["n_sessions"] == 1
    assert avg["avg"] == 1.0  # (1.5 + -0.5) BB numa única sessão/dia


def test_normalized_insufficient_sample_never_fabricates_value():
    conn = dbm.connect(TEST_DSN)
    _setup_money_scenario(conn)  # só 2 torneios com resultado, mínimo é 30
    out = bankroll.normalized_result(conn, basis="per_100_tournaments", unit="money")
    assert out["insufficient"] is True
    assert out["value"] is None
    assert out["n"] == 2


def test_normalized_per_1000_hands_rejects_non_bb_unit():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    out = bankroll.normalized_result(conn, basis="per_1000_hands", unit="money")
    assert out["insufficient"] is True
    assert out["value"] is None
    assert out["reason"]


def test_bankroll_series_money_currency_filter_never_mixes():
    """Sem tabela de câmbio, USD e BRL não podem ser somados juntos —
    o filtro de moeda isola cada série."""
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    _insert_tournament(conn, "T1", 10, "USD", "2026-01-01T10:00:00", 1, 30)   # +20 USD
    _insert_tournament(conn, "T2", 50, "BRL", "2026-01-01T10:00:00", 1, 100)  # +50 BRL
    conn.commit()
    usd = bankroll.bankroll_series(conn, unit="money", currency="USD")
    brl = bankroll.bankroll_series(conn, unit="money", currency="BRL")
    assert usd == [{"period": "2026-01-01", "value": 20.0, "cumulative": 20.0, "n": 1}]
    assert brl == [{"period": "2026-01-01", "value": 50.0, "cumulative": 50.0, "n": 1}]
    # sem filtro, soma as duas moedas no mesmo dia (comportamento
    # documentado — cabe ao frontend pedir o filtro quando há >1 moeda)
    mixed = bankroll.bankroll_series(conn, unit="money")
    assert mixed[0]["value"] == 70.0


def test_downswing_with_recovery_after_trough():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    _insert_tournament(conn, "T1", 10, "USD", "2026-01-01T10:00:00", 1, 30)   # +20, cum 20
    _insert_tournament(conn, "T2", 50, "USD", "2026-01-02T10:00:00", 5, 0)    # -50, cum -30 (vale)
    _insert_tournament(conn, "T3", 10, "USD", "2026-01-03T10:00:00", 1, 60)   # +50, cum 20 (recupera exatamente o pico)
    conn.commit()
    d = bankroll.downswing(conn, unit="money")
    assert d["value"] == 50.0
    assert d["start"] == "2026-01-01"
    assert d["trough"] == "2026-01-02"
    assert d["recovery"] == "2026-01-03"


def test_bankroll_series_empty_when_no_registered_tournaments():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    _insert_tournament(conn, "T1", 10, "USD", "2026-01-01T10:00:00", None, None)
    conn.commit()
    assert bankroll.bankroll_series(conn, unit="money") == []
    assert bankroll.bankroll_series(conn, unit="buyins") == []
    assert bankroll.downswing(conn, unit="money") is None
    avg = bankroll.session_average(conn, unit="money")
    assert avg["avg"] is None and avg["n_excluded"] == 1


def test_distinct_currencies_only_counts_registered_results():
    conn = dbm.connect(TEST_DSN)
    _setup_money_scenario(conn)
    currencies = bankroll.distinct_currencies(conn)
    assert currencies == [{"currency": "USD", "tournaments": 2}]  # T3 sem resultado não conta


if __name__ == "__main__":
    test_bankroll_series_money_excludes_unregistered_and_accumulates()
    test_bankroll_series_buyins_self_normalizes_per_tournament()
    test_bankroll_series_money_currency_filter_never_mixes()
    test_downswing_finds_peak_to_trough()
    test_downswing_none_below_two_points()
    test_session_average_excludes_sessions_without_result_not_zero()
    test_session_average_bb_includes_every_session()
    test_downswing_with_recovery_after_trough()
    test_bankroll_series_empty_when_no_registered_tournaments()
    test_normalized_insufficient_sample_never_fabricates_value()
    test_normalized_per_1000_hands_rejects_non_bb_unit()
    test_distinct_currencies_only_counts_registered_results()
    print("OK: todos os testes de bankroll passaram")
