"""Bankroll em caixa (re-buys + entradas/prêmios em ticket) contra o
Postgres de teste — mesmo padrão de test_bankroll.py.

Cenário central é o caso real que motivou a feature: freeroll paga ticket
de $0.55, ticket usado num torneio de $0.55 que paga ticket de $3.30 —
o caixa não muda (nada foi gasto, nada virou dinheiro), mas o "resultado"
por valor de face soma os dois prêmios."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import bankroll, stats
from poker_coach import db as dbm

TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"
SITE = "testsite"


def _reset(conn):
    for t in ["actions", "seats", "showdowns", "results", "hands", "tournaments"]:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


def _t(conn, tid, buyin, day, *, pos=None, prize=None, prize_type=None):
    conn.execute(
        """INSERT INTO tournaments (site, tournament_id, buyin, currency, first_seen, last_seen,
                                     finish_position, prize, prize_type)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (SITE, tid, buyin, "$", f"{day}T10:00:00", f"{day}T11:00:00", pos, prize, prize_type),
    )


@pytest.fixture
def conn():
    c = dbm.connect(TEST_DSN)
    _reset(c)
    yield c
    c.close()


def test_ticket_chain_does_not_inflate_cash(conn):
    _t(conn, "FREE", 0.0, "2026-01-01", pos=1, prize=0.55, prize_type="ticket")
    _t(conn, "SAT", 0.55, "2026-01-02", pos=1, prize=3.30, prize_type="ticket")
    dbm.set_tournament_entry(conn, SITE, "SAT", rebuys=0, entry_type="ticket",
                             ticket_site=SITE, ticket_tournament_id="FREE")
    conn.commit()

    c = bankroll.cash_summary(conn)
    assert c["cash_profit"] == 0.0
    assert c["cash_out"] == 0.0 and c["cash_in"] == 0.0
    assert c["tickets_won"] == 2 and c["tickets_won_value"] == 3.85
    # ticket de $0.55 foi consumido; o de $3.30 ainda não foi vinculado a nada
    assert c["tickets_unlinked"] == 1 and c["tickets_unlinked_value"] == 3.3
    assert c["ticket_entries"] == 1 and c["ticket_entries_linked"] == 1
    # visão de resultado (valor de face) continua somando os prêmios
    assert stats.roi(conn)["profit"] == pytest.approx(3.30)


def test_rebuys_cost_cash_and_result(conn):
    # buy-in 1.10 + 2 re-buys = 3.30 gastos; prêmio em dinheiro 5.00
    _t(conn, "T1", 1.1, "2026-01-01", pos=3, prize=5.0, prize_type="cash")
    dbm.set_tournament_entry(conn, SITE, "T1", rebuys=2, entry_type="cash")
    conn.commit()

    c = bankroll.cash_summary(conn)
    assert c["rebuys"] == 2 and c["rebuys_cost"] == 2.2
    assert c["cash_out"] == 3.3 and c["cash_profit"] == 1.7
    r = stats.roi(conn)
    assert r["invested"] == 3.3 and r["profit"] == 1.7


def test_cash_counts_buyin_of_tournament_without_result(conn):
    _t(conn, "WIN", 1.0, "2026-01-01", pos=1, prize=4.0, prize_type="cash")
    _t(conn, "PENDING", 2.0, "2026-01-02")  # jogado, resultado nunca lançado
    conn.commit()

    c = bankroll.cash_summary(conn)
    assert c["pending_results"] == 1 and c["pending_buyins"] == 2.0
    assert c["cash_profit"] == 1.0
    series = bankroll.bankroll_series(conn, unit="cash")
    assert [(r["period"], r["value"], r["cumulative"]) for r in series] == [
        ("2026-01-01", 3.0, 3.0), ("2026-01-02", -2.0, 1.0)]
    # a visão de resultado ("money") continua ignorando o torneio pendente
    assert [r["period"] for r in bankroll.bankroll_series(conn, unit="money")] == ["2026-01-01"]


def test_prize_without_position_counts_as_registered_result(conn):
    _t(conn, "T1", 1.0, "2026-01-01", prize=0.0)  # bust lançado só com prêmio 0
    conn.commit()
    assert stats.roi(conn)["tournaments"] == 1
    assert stats.results_pending(conn) == []


def test_entry_validation(conn):
    _t(conn, "SRC", 0.0, "2026-01-01", pos=1, prize=0.55, prize_type="ticket")
    _t(conn, "CASHPRIZE", 0.0, "2026-01-01", pos=1, prize=1.0, prize_type="cash")
    _t(conn, "A", 0.55, "2026-01-02")
    _t(conn, "B", 0.55, "2026-01-03")
    conn.commit()

    with pytest.raises(ValueError):
        dbm.set_tournament_entry(conn, SITE, "A", rebuys=-1, entry_type="cash")
    with pytest.raises(ValueError):  # vínculo exige entrada via ticket
        dbm.set_tournament_entry(conn, SITE, "A", rebuys=0, entry_type="cash",
                                 ticket_site=SITE, ticket_tournament_id="SRC")
    with pytest.raises(ValueError):  # origem sem prêmio ticket
        dbm.set_tournament_entry(conn, SITE, "A", rebuys=0, entry_type="ticket",
                                 ticket_site=SITE, ticket_tournament_id="CASHPRIZE")
    with pytest.raises(ValueError):  # próprio ticket
        dbm.set_tournament_entry(conn, SITE, "SRC", rebuys=0, entry_type="ticket",
                                 ticket_site=SITE, ticket_tournament_id="SRC")
    with pytest.raises(LookupError):
        dbm.set_tournament_entry(conn, SITE, "NOPE", rebuys=0, entry_type="cash")

    dbm.set_tournament_entry(conn, SITE, "A", rebuys=0, entry_type="ticket",
                             ticket_site=SITE, ticket_tournament_id="SRC")
    with pytest.raises(ValueError, match="já foi usado"):  # ticket só vale uma vez
        dbm.set_tournament_entry(conn, SITE, "B", rebuys=0, entry_type="ticket",
                                 ticket_site=SITE, ticket_tournament_id="SRC")
    # re-salvar o mesmo torneio com o mesmo ticket é permitido (idempotente)
    dbm.set_tournament_entry(conn, SITE, "A", rebuys=1, entry_type="ticket",
                             ticket_site=SITE, ticket_tournament_id="SRC")
    src = dbm.ticket_sources(conn)
    assert [(s["tournament_id"], s["used_by_tournament_id"]) for s in src] == [("SRC", "A")]
