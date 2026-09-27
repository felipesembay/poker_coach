"""Testes de poker_coach/player_stats.py — funções puras (sem banco):
posição recalculada via Hand.position_order, flags de oportunidade/ação
por métrica e agregação com denominador correto."""
import datetime as dt
import pathlib
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import player_stats as ps
from poker_coach.models import Seat


def _seats(n):
    return [Seat(i, f"P{i}", 1000) for i in range(1, n + 1)]


def _pre(*pairs):
    return [("preflop", p, a) for p, a in pairs]


def _flop(*pairs):
    return [("flop", p, a) for p, a in pairs]


# ---------------- posição ----------------

def test_positions_short_handed_never_utg():
    # botão no assento 1; ordem a partir do botão: BTN, SB, BB, ...
    assert ps.positions_by_player(1, _seats(6)) == {
        "P1": "BTN", "P2": "SB", "P3": "BB", "P4": "UTG", "P5": "HJ", "P6": "CO"}
    assert ps.positions_by_player(1, _seats(5)) == {
        "P1": "BTN", "P2": "SB", "P3": "BB", "P4": "HJ", "P5": "CO"}
    assert ps.positions_by_player(1, _seats(4)) == {
        "P1": "BTN", "P2": "SB", "P3": "BB", "P4": "CO"}
    assert ps.positions_by_player(1, _seats(3)) == {"P1": "BTN", "P2": "SB", "P3": "BB"}


def test_positions_heads_up_button_is_btn_sb():
    # HU: o botão é o small blind — categoria própria, separada de BTN e SB.
    assert ps.positions_by_player(2, _seats(2)) == {"P2": "BTN/SB", "P1": "BB"}


def test_positions_relative_to_button_not_seat_number():
    seats = [Seat(2, "A", 1), Seat(5, "B", 1), Seat(7, "C", 1), Seat(9, "Hero", 1)]
    assert ps.positions_by_player(7, seats) == {"C": "BTN", "Hero": "SB", "A": "BB", "B": "CO"}


def test_stack_range_edges():
    assert ps.stack_range(7.99) == "<8 BB"
    assert ps.stack_range(8) == "8–12 BB"
    assert ps.stack_range(15) == "15–20 BB"
    assert ps.stack_range(30) == "30+ BB"
    assert ps.stack_range(None) is None


# ---------------- flags por mão ----------------

POS6 = {"U": "UTG", "H": "HJ", "C": "CO", "B": "BTN", "S": "SB", "BB": "BB"}


def _flags(hero, actions, positions=POS6):
    return ps.hand_flags(hero, positions, actions)


def test_walk_is_not_vpip_opportunity():
    f = _flags("BB", _pre(("U", "fold"), ("H", "fold"), ("C", "fold"), ("B", "fold"), ("S", "fold")))
    assert f["vpip_opp"] == 0 and f["vpip"] == 0


def test_open_raise_counts_vpip_pfr_and_ats_on_btn():
    f = _flags("B", _pre(("U", "fold"), ("H", "fold"), ("C", "fold"), ("B", "raise")))
    assert (f["vpip_opp"], f["vpip"], f["pfr"]) == (1, 1, 1)
    assert (f["ats_opp"], f["ats"]) == (1, 1)
    assert f["threebet_opp"] == 0


def test_limp_is_not_steal_and_utg_has_no_ats_opportunity():
    f = _flags("B", _pre(("U", "fold"), ("H", "fold"), ("C", "fold"), ("B", "call")))
    assert (f["ats_opp"], f["ats"], f["vpip"], f["pfr"]) == (1, 0, 1, 0)
    f = _flags("U", _pre(("U", "raise")))
    assert f["ats_opp"] == 0


def test_limper_before_kills_ats_opportunity():
    f = _flags("B", _pre(("U", "call"), ("H", "fold"), ("C", "fold"), ("B", "raise")))
    assert f["ats_opp"] == 0


def test_threebet_opportunity_and_made():
    f = _flags("C", _pre(("U", "raise"), ("H", "fold"), ("C", "raise")))
    assert (f["threebet_opp"], f["threebet"]) == (1, 1)
    f = _flags("C", _pre(("U", "raise"), ("H", "fold"), ("C", "call")))
    assert (f["threebet_opp"], f["threebet"]) == (1, 0)


def test_facing_three_bet_is_not_threebet_opportunity():
    f = _flags("C", _pre(("U", "raise"), ("H", "raise"), ("C", "fold")))
    assert f["threebet_opp"] == 0


def test_fold_to_three_bet():
    f = _flags("U", _pre(("U", "raise"), ("H", "raise"), ("C", "fold"), ("B", "fold"),
                         ("S", "fold"), ("BB", "fold"), ("U", "fold")))
    assert (f["f3b_opp"], f["f3b"]) == (1, 1)
    # 4-bet em vez de fold
    f = _flags("U", _pre(("U", "raise"), ("H", "raise"), ("U", "raise")))
    assert (f["f3b_opp"], f["f3b"]) == (1, 0)
    # herói não abriu (só limpou): não é fold to 3-bet
    f = _flags("U", _pre(("U", "call"), ("H", "raise"), ("C", "raise"), ("U", "fold")))
    assert f["f3b_opp"] == 0


def test_fold_to_steal():
    f = _flags("BB", _pre(("U", "fold"), ("H", "fold"), ("C", "fold"), ("B", "raise"),
                          ("S", "fold"), ("BB", "fold")))
    assert (f["fts_opp"], f["fts"]) == (1, 1)
    # raise do UTG não é steal
    f = _flags("BB", _pre(("U", "raise"), ("H", "fold"), ("C", "fold"), ("B", "fold"),
                          ("S", "fold"), ("BB", "fold")))
    assert f["fts_opp"] == 0
    # call no meio: não é steal puro
    f = _flags("BB", _pre(("U", "fold"), ("H", "fold"), ("C", "raise"), ("B", "call"),
                          ("S", "fold"), ("BB", "fold")))
    assert f["fts_opp"] == 0


def test_heads_up_steal_and_fold_to_steal():
    pos = {"Hero": "BTN/SB", "V": "BB"}
    f = _flags("Hero", _pre(("Hero", "raise"), ("V", "fold")), pos)
    assert (f["ats_opp"], f["ats"]) == (1, 1)
    f = _flags("V", _pre(("Hero", "raise"), ("V", "fold")), pos)
    assert (f["fts_opp"], f["fts"]) == (1, 1)


def test_cbet():
    pre = _pre(("U", "fold"), ("H", "fold"), ("C", "raise"), ("B", "fold"), ("S", "fold"), ("BB", "call"))
    f = _flags("C", pre + _flop(("BB", "check"), ("C", "bet")))
    assert (f["cbet_opp"], f["cbet"]) == (1, 1)
    f = _flags("C", pre + _flop(("BB", "check"), ("C", "check")))
    assert (f["cbet_opp"], f["cbet"]) == (1, 0)
    # donk bet: sem oportunidade de c-bet
    f = _flags("C", pre + _flop(("BB", "bet"), ("C", "call")))
    assert f["cbet_opp"] == 0
    # sem raise preflop (pote limpado): ninguém tem c-bet
    f = _flags("BB", _pre(("S", "call"), ("BB", "check")) + _flop(("S", "check"), ("BB", "bet")))
    assert f["cbet_opp"] == 0


def test_fold_to_cbet():
    pre = _pre(("U", "fold"), ("H", "fold"), ("C", "raise"), ("B", "fold"), ("S", "fold"), ("BB", "call"))
    f = _flags("BB", pre + _flop(("BB", "check"), ("C", "bet"), ("BB", "fold")))
    assert (f["fcb_opp"], f["fcb"]) == (1, 1)
    f = _flags("BB", pre + _flop(("BB", "check"), ("C", "bet"), ("BB", "call")))
    assert (f["fcb_opp"], f["fcb"]) == (1, 0)
    # agressor deu check: não houve c-bet
    f = _flags("BB", pre + _flop(("BB", "check"), ("C", "check")))
    assert f["fcb_opp"] == 0


def test_preflop_allin_has_no_postflop_opportunity():
    pre = _pre(("U", "fold"), ("H", "fold"), ("C", "raise"), ("B", "fold"), ("S", "fold"), ("BB", "call"))
    f = _flags("C", pre)  # sem ações no flop (all-in preflop)
    assert f["cbet_opp"] == 0 and f["fcb_opp"] == 0


# ---------------- agregação ----------------

def _df(rows):
    base = dict.fromkeys(ps.FLAG_COLUMNS, 0)
    out = []
    for r in rows:
        row = {"site": "s", "tournament_id": "T1", "buyin": 1.1, "ts": "2026-09-01T10:00:00",
               "stack_range": "8–12 BB", "position": "CO", **base}
        row.update(r)
        out.append(row)
    df = pd.DataFrame(out)
    df["ts"] = pd.to_datetime(df["ts"])
    return df


def test_summarize_uses_metric_specific_denominator():
    df = _df([
        {"vpip_opp": 1, "vpip": 1, "pfr": 1, "threebet_opp": 1, "threebet": 1},
        {"vpip_opp": 1, "vpip": 1},
        {"vpip_opp": 1},
        {"vpip_opp": 1, "threebet_opp": 1},
        {},  # walk
    ])
    s = ps.summarize(df)
    assert s["hands"] == 5
    assert s["vpip"] == {"pct": 50.0, "made": 2, "opps": 4}
    assert s["pfr"] == {"pct": 25.0, "made": 1, "opps": 4}
    assert s["threebet"] == {"pct": 50.0, "made": 1, "opps": 2}
    assert s["f3b"]["pct"] is None and s["f3b"]["opps"] == 0
    assert s["gap"] == 25.0


def test_filters_combine():
    df = _df([
        {"buyin": 5.5, "stack_range": "8–12 BB", "position": "CO", "ts": "2026-09-20T10:00:00"},
        {"buyin": 5.5, "stack_range": "8–12 BB", "position": "BTN"},
        {"buyin": 1.1, "stack_range": "8–12 BB", "position": "CO"},
        {"buyin": 5.5, "stack_range": "30+ BB", "position": "CO"},
    ])
    out = ps.apply_filters(df, buyin=5.5, stack="8–12 BB", position="CO")
    assert len(out) == 1
    start, end = ps.period_bounds("7d", dt.date(2026, 9, 21))
    assert len(ps.apply_filters(df, start=start, end=end)) == 1
    assert len(ps.apply_filters(df, start=dt.date(2026, 9, 1), end=dt.date(2026, 9, 1))) == 3


def test_long_format_drops_small_samples():
    df = _df([{"vpip_opp": 1, "vpip": 1, "threebet_opp": 1}] * 3)
    by = ps.summarize_by(df, ["position"])
    lf = ps.long_format(by, "position", ["vpip", "threebet"], min_opps=3)
    assert set(lf["métrica"]) == {"VPIP", "3-Bet"}
    lf = ps.long_format(by, "position", ["vpip", "f3b"], min_opps=4)
    assert lf.empty
