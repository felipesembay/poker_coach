"""Replayer: busca de mãos + estado completo passo a passo (mesa, stacks,
pot, board) + Painel IA (reusa o Push/Fold, mesmo escopo/limitações).

Sem árvore de decisão com branches (raise->fold/call/3bet): a hand
history só grava a linha que realmente aconteceu, não contrafactuais.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm, replay  # noqa: E402
from poker_coach.pushfold import analyze as pf  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/replayer", tags=["replayer"])


def _conn():
    return dbm.connect(DSN)


class HandSummaryOut(BaseModel):
    site: str
    hand_id: str
    tournament_id: str
    tournament_name: str | None
    buyin: float | None
    ts: str | None
    position: str | None
    hero_cards: str | None
    stack_bb: float | None
    net_bb: float
    favorite: bool
    board: str | None
    n_players: int | None
    showdown: bool
    all_in: bool


@router.get("/search", response_model=list[HandSummaryOut])
def search(site: str | None = None, tournament_id: str | None = None,
           position: str | None = None, bb_min: float | None = None,
           bb_max: float | None = None, n_players: int | None = None,
           result: str | None = None, tag: str | None = None, q: str | None = None,
           favorite: bool | None = None, showdown: bool | None = None,
           all_in: bool | None = None, date_from: str | None = None,
           date_to: str | None = None, limit: int = Query(300, le=500)):
    conn = _conn()
    try:
        rows = replay.list_hands(
            conn, site=site, tournament_id=tournament_id, position=position,
            bb_min=bb_min, bb_max=bb_max, n_players=n_players, result=result,
            tag=tag, q=q, favorite=favorite, showdown=showdown, all_in=all_in,
            date_from=date_from, date_to=date_to, limit=limit,
        )
        return [HandSummaryOut(**r) for r in rows]
    finally:
        conn.close()


class SeatOut(BaseModel):
    seat_no: int
    player: str
    starting_stack: int
    position: str | None
    is_hero: bool
    cards: str | None  # só quando conhecidas (herói sempre; vilão só se showdown)


class StepOut(BaseModel):
    order: int
    street: str
    player: str
    position: str | None
    action: str
    amount: int
    all_in: bool
    pot_after: int
    stacks_after: dict[str, int]
    board_so_far: str


class PainelIaOut(BaseModel):
    in_scope: bool
    reason: str | None = None
    hero_decision: str | None = None
    nash_decision: str | None = None
    ev_push_bb: float | None = None
    ev_lost_bb: float | None = None


class ReplayHandOut(BaseModel):
    site: str
    hand_id: str
    tournament_id: str
    tournament_name: str | None
    buyin: float | None
    ts: str | None
    sb: int
    bb: int
    ante: int
    hero: str | None
    hero_cards: str | None
    board: str | None
    seats: list[SeatOut]
    steps: list[StepOut]
    street_first_index: dict[str, int]
    painel_ia: PainelIaOut
    note: str
    tags: list[str]
    favorite: bool


@router.get("/{site}/{hand_id}", response_model=ReplayHandOut)
def get_hand(site: str, hand_id: str):
    conn = _conn()
    try:
        rh = replay.load(conn, site, hand_id)
        if rh is None:
            raise HTTPException(404, "Mão não encontrada.")

        seats_out = [
            SeatOut(
                seat_no=s.seat_no, player=s.player, starting_stack=s.stack,
                position=rh.positions.get(s.player), is_hero=(s.player == rh.hero),
                cards=rh.hero_cards if s.player == rh.hero else rh.shown_cards.get(s.player),
            ) for s in rh.seats
        ]
        steps_out = [
            StepOut(order=s.order, street=s.street, player=s.player, position=s.position,
                    action=s.action, amount=s.amount, all_in=s.all_in, pot_after=s.pot_after,
                    stacks_after=s.stacks_after, board_so_far=s.board_so_far)
            for s in rh.steps
        ]

        ia_row = pf.analyze_hand_row(conn, site, hand_id, precise=True)
        if ia_row is None:
            painel = PainelIaOut(
                in_scope=False,
                reason="Fora do escopo do motor (só cobre a decisão de abrir o pote "
                       "preflop, primeiro a agir). Sem motor pós-flop/ICM/3bet ainda "
                       "nesse painel — ICM tem endpoint próprio em /api/icm.",
            )
        else:
            painel = PainelIaOut(
                in_scope=True, hero_decision=ia_row.hero_decision,
                nash_decision=ia_row.nash_decision, ev_push_bb=ia_row.ev_push_bb,
                ev_lost_bb=ia_row.ev_lost_bb,
            )

        return ReplayHandOut(
            site=rh.site, hand_id=rh.hand_id, tournament_id=rh.tournament_id,
            tournament_name=rh.tournament_name, buyin=rh.buyin, ts=rh.ts,
            sb=rh.sb, bb=rh.bb, ante=rh.ante, hero=rh.hero, hero_cards=rh.hero_cards,
            board=rh.board, seats=seats_out, steps=steps_out,
            street_first_index=rh.street_first_index, painel_ia=painel,
            note=dbm.get_note(conn, site, hand_id), tags=dbm.get_tags(conn, site, hand_id),
            favorite=bool(conn.execute(
                "SELECT favorite FROM hands WHERE site=? AND hand_id=?", (site, hand_id)
            ).fetchone()[0]),
        )
    finally:
        conn.close()
