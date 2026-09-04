"""Aplica o motor de ICM às mãos reais de um torneio — só faz sentido
pra mesa final (ver limitação em poker_coach/icm.py). Espelha a
estrutura de poker_coach/pushfold/analyze.py, mas em $ (ICM) em vez de
BB (chip EV), usando o stack de TODOS os jogadores da mesa (ICM precisa
do campo inteiro, não só herói+BB).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import icm
from .models import Hand, Seat
from .pushfold import analyze as pf
from .pushfold import equity as eq

DEFAULT_MAX_BB = 40.0


@dataclass
class ICMLeakRow:
    site: str
    hand_id: str
    tournament_id: str
    ts: str | None
    position: str
    hero_cards: str
    effective_bb: float
    n_players: int
    hero_decision: str      # "push" | "fold"
    icm_decision: str        # "push" | "fold"
    icm_ev_fold: float        # $ de dar fold (= equity ICM atual)
    icm_ev_push: float         # $ de empurrar
    icm_ev_lost: float          # 0 se a decisão bateu com o ICM
    risk_premium_pct: float      # quanto ICM pede mais tight que chip EV, agora


def _bb_seat(seats: list[Seat], button_seat: int) -> Seat | None:
    stub = Hand(site="", hand_id="", tournament_id="", timestamp=None, level=None,
                sb=0, bb=0, ante=0, buyin=None, currency=None, table_name=None,
                max_players=None, button_seat=button_seat, seats=seats)
    return stub.seat_at_position("BB")


def analyze_icm_hand_row(conn: sqlite3.Connection, site: str, hand_id: str,
                          payouts: list[float], max_bb: float = DEFAULT_MAX_BB
                          ) -> ICMLeakRow | None:
    """Mesmo escopo do motor de chip EV (spot de abertura, vilão=BB) —
    ver poker_coach/pushfold/analyze.py. A diferença é usar o stack de
    TODOS os jogadores da mesa (não só herói+BB) pra rodar o ICM."""
    row = conn.execute(
        """SELECT tournament_id, hero, hero_cards, hero_position, hero_stack_bb,
                  bb, button_seat, ts
           FROM hands WHERE site=? AND hand_id=?""",
        (site, hand_id),
    ).fetchone()
    if row is None:
        return None
    tid, hero, hero_cards_s, hero_pos, hero_stack_bb, bb, button_seat, ts = row
    if not hero or not hero_cards_s or not hero_pos or hero_pos == "BB" or not bb:
        return None

    seats = [Seat(seat_no, player, stack) for seat_no, player, stack in conn.execute(
        "SELECT seat_no, player, stack FROM seats WHERE site=? AND hand_id=?",
        (site, hand_id))]
    if not seats:
        return None
    bb_seat = _bb_seat(seats, button_seat)
    if bb_seat is None or bb_seat.player == hero:
        return None

    acts = conn.execute(
        """SELECT player, action, amount, all_in FROM actions
           WHERE site=? AND hand_id=? AND street='preflop' ORDER BY ord""",
        (site, hand_id),
    ).fetchall()

    dead = {}
    pot_before = 0
    hero_action = None
    unopened = True
    for player, action, amount, all_in in acts:
        if action in ("post_sb", "post_bb", "post_ante"):
            dead[player] = dead.get(player, 0) + amount
            pot_before += amount
            continue
        if player == hero:
            hero_action = action
            break
        if action in ("raise", "bet", "allin", "call"):
            unopened = False
            break
    if not unopened or hero_action not in ("fold", "raise", "allin"):
        return None

    hero_dead = dead.get(hero, 0)
    bbp_dead = dead.get(bb_seat.player, 0)
    hero_remaining_bb = hero_stack_bb - hero_dead / bb
    bb_remaining_bb = bb_seat.stack / bb - bbp_dead / bb
    effective_bb = min(hero_remaining_bb, bb_remaining_bb)
    pot_bb = pot_before / bb
    if effective_bb <= 1 or effective_bb > max_bb:
        return None

    hero_cards = eq.parse_hand(hero_cards_s)
    if len(hero_cards) != 2:
        return None

    # stacks (em fichas) de TODOS os jogadores, já descontando o que
    # postaram até agora — mesma convenção do motor de chip EV.
    stacks_now = [s.stack - dead.get(s.player, 0) for s in seats]
    players = [s.player for s in seats]
    hero_idx = players.index(hero)
    villain_idx = players.index(bb_seat.player)
    effective_chips = int(round(effective_bb * bb))

    result = pf._cached_solve(round(effective_bb * 2) / 2, round(pot_bb * 4) / 4)
    p_call = result.call_pct / 100
    hcls = eq.class_of(hero_cards)
    equity_vs_range = eq.equity_class_vs_range(hcls, result.call_classes, pf._matrix())

    icm_ev_fold, icm_ev_push = icm.push_fold_icm_ev(
        stacks_now, payouts, hero_idx, villain_idx, effective_chips, pot_before,
        equity_vs_range, p_call)

    hero_decision = "push" if hero_action in ("raise", "allin") else "fold"
    icm_decision = "push" if icm_ev_push > icm_ev_fold else "fold"
    diff = icm_ev_push - icm_ev_fold
    if hero_decision == "fold" and diff > 0:
        icm_ev_lost = diff
    elif hero_decision == "push" and diff < 0:
        icm_ev_lost = -diff
    else:
        icm_ev_lost = 0.0

    rp = icm.risk_premium_pct(stacks_now, payouts, hero_idx)

    return ICMLeakRow(
        site=site, hand_id=hand_id, tournament_id=tid, ts=ts, position=hero_pos,
        hero_cards=hero_cards_s, effective_bb=round(effective_bb, 1), n_players=len(seats),
        hero_decision=hero_decision, icm_decision=icm_decision,
        icm_ev_fold=round(icm_ev_fold, 2), icm_ev_push=round(icm_ev_push, 2),
        icm_ev_lost=round(icm_ev_lost, 2), risk_premium_pct=rp,
    )


def analyze_icm_tournament(conn: sqlite3.Connection, site: str, tournament_id: str,
                            payouts: list[float], max_table_size: int = 9,
                            max_bb: float = DEFAULT_MAX_BB) -> list[ICMLeakRow]:
    """Roda o ICM sobre as mãos de abertura desse torneio ONDE a mesa
    tinha `max_table_size` jogadores ou menos — heurística de "provável
    mesa final", não uma certeza (ver limitação do módulo). Quem chama
    já devia ter pedido confirmação explícita ao usuário antes disso."""
    candidates = conn.execute(
        """SELECT site, hand_id FROM hands
           WHERE site=? AND tournament_id=? AND hero_position IS NOT NULL
             AND hero_position != 'BB' AND n_players <= ?""",
        (site, tournament_id, max_table_size),
    ).fetchall()
    out = []
    for s, hand_id in candidates:
        r = analyze_icm_hand_row(conn, s, hand_id, payouts, max_bb=max_bb)
        if r is not None:
            out.append(r)
    return out


def summarize_icm(rows: list[ICMLeakRow]) -> dict:
    total_lost = sum(r.icm_ev_lost for r in rows)
    leaks = [r for r in rows if r.icm_ev_lost > 0]
    return {
        "spots": len(rows),
        "total_ev_lost": round(total_lost, 2),
        "leak_spots": len(leaks),
        "worst": sorted(leaks, key=lambda r: -r.icm_ev_lost)[:20],
        "rows": rows,
    }
