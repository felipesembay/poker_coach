"""Hand browser + mutações compartilhadas (favorito/nota/tags) — usadas
tanto pela página de Mãos quanto pelo Replayer/Tags/Favoritos, um único
lugar de escrita.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/hands", tags=["hands"])


def _conn():
    return dbm.connect(DSN)


def _street_reached(board: str | None, showdown: bool) -> str:
    if showdown:
        return "Showdown"
    n = len((board or "").split())
    return {0: "Preflop", 3: "Flop", 4: "Turn", 5: "River"}.get(n, "Preflop")


class HandOut(BaseModel):
    site: str
    hand_id: str
    hand_display_id: str  # "#" + hand_id, casa com o mock (handId: "#48219301")
    tournament: str
    tournament_id: str
    position: str | None
    stack_bb: float | None
    cards: list[str]
    board: list[str]
    result_bb: float
    all_in: bool
    showdown: bool
    tags: list[str]
    street: str
    favorite: bool


@router.get("", response_model=list[HandOut])
def list_hands(
    site: str | None = None, position: str | None = None,
    bb_min: float | None = None, bb_max: float | None = None,
    tag: str | None = None, favorite_only: bool = False, showdown_only: bool = False,
    all_in_only: bool = False,
    date_from: str | None = None, date_to: str | None = None,
    limit: int = Query(50, le=500), offset: int = Query(0, ge=0),
):
    conn = _conn()
    try:
        where = ["1=1"]
        params: list = []
        if site:
            where.append("h.site=?"); params.append(site)
        if position:
            where.append("h.hero_position=?"); params.append(position)
        if bb_min is not None:
            where.append("h.hero_stack_bb>=?"); params.append(bb_min)
        if bb_max is not None:
            where.append("h.hero_stack_bb<=?"); params.append(bb_max)
        if favorite_only:
            where.append("h.favorite=1")
        if date_from:
            where.append("h.ts>=?"); params.append(date_from)
        if date_to:
            where.append("h.ts<=?"); params.append(date_to + "T23:59:59")
        if tag:
            where.append("EXISTS (SELECT 1 FROM tags t WHERE t.site=h.site "
                          "AND t.hand_id=h.hand_id AND t.tag=?)")
            params.append(tag)
        sd_expr = ("EXISTS (SELECT 1 FROM showdowns sd WHERE sd.site=h.site "
                   "AND sd.hand_id=h.hand_id AND sd.player=h.hero)")
        if showdown_only:
            where.append(sd_expr)
        ai_expr = ("EXISTS (SELECT 1 FROM actions a WHERE a.site=h.site "
                   "AND a.hand_id=h.hand_id AND a.player=h.hero AND a.all_in=1)")
        if all_in_only:
            where.append(ai_expr)

        sql = f"""SELECT h.site, h.hand_id, h.tournament_id, COALESCE(t.name, h.tournament_id),
                         h.hero_position, h.hero_cards, h.hero_stack_bb, h.board,
                         CAST(h.hero_net_chips AS REAL) / h.bb AS net_bb, h.favorite,
                         {sd_expr} AS showdown, {ai_expr} AS all_in
                  FROM hands h LEFT JOIN tournaments t
                    ON t.site = h.site AND t.tournament_id = h.tournament_id
                  WHERE {' AND '.join(where)} AND h.bb > 0
                  ORDER BY h.ts DESC LIMIT ? OFFSET ?"""
        params += [limit, offset]
        rows = conn.execute(sql, params).fetchall()

        out = []
        for (s, hid, tid, tname, pos, cards, stack_bb, board, net_bb, fav,
             showdown, all_in) in rows:
            out.append(HandOut(
                site=s, hand_id=hid, hand_display_id=f"#{hid}", tournament=tname,
                tournament_id=tid, position=pos, stack_bb=stack_bb,
                cards=(cards or "").split(), board=(board or "").split(),
                result_bb=round(net_bb or 0, 1), all_in=bool(all_in), showdown=bool(showdown),
                tags=dbm.get_tags(conn, s, hid), street=_street_reached(board, bool(showdown)),
                favorite=bool(fav),
            ))
        return out
    finally:
        conn.close()


class FavoriteIn(BaseModel):
    favorite: bool


@router.put("/{site}/{hand_id}/favorite")
def set_favorite(site: str, hand_id: str, payload: FavoriteIn):
    conn = _conn()
    try:
        dbm.set_favorite(conn, site, hand_id, payload.favorite)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


class NoteIn(BaseModel):
    text: str


@router.put("/{site}/{hand_id}/note")
def set_note(site: str, hand_id: str, payload: NoteIn):
    conn = _conn()
    try:
        dbm.set_note(conn, site, hand_id, payload.text)
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


class TagsIn(BaseModel):
    tags: list[str]


@router.put("/{site}/{hand_id}/tags")
def set_tags(site: str, hand_id: str, payload: TagsIn):
    conn = _conn()
    try:
        dbm.set_tags(conn, site, hand_id, payload.tags)
        conn.commit()
        return {"ok": True, "tags": payload.tags}
    finally:
        conn.close()
