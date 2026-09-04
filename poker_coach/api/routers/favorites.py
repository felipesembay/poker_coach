"""Favoritos: só mãos (hands.favorite=true). O mock tem tipos "Estudo" e
"Drill" além de "Mão" — esses módulos não existem no backend ainda
(biblioteca de estudos/drills não foi construída), então não fingimos
retornar isso aqui."""
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


class FavoriteOut(BaseModel):
    site: str
    hand_id: str
    type: str  # sempre "Mão" por enquanto
    title: str
    meta: str
    tags: list[str]


@router.get("", response_model=list[FavoriteOut])
def list_favorites():
    conn = dbm.connect(DSN)
    try:
        rows = conn.execute(
            """SELECT h.site, h.hand_id, h.hero_position, h.hero_cards, h.tournament_id,
                      CAST(h.hero_net_chips AS REAL) / h.bb AS net_bb
               FROM hands h WHERE h.favorite = 1 AND h.bb > 0
               ORDER BY h.ts DESC"""
        ).fetchall()
        out = []
        for site, hid, pos, cards, tid, net_bb in rows:
            out.append(FavoriteOut(
                site=site, hand_id=hid, type="Mão",
                title=f"{cards or ''} no {pos or '?'}",
                meta=f"Torneio {tid} · {net_bb:+.1f} BB",
                tags=dbm.get_tags(conn, site, hid),
            ))
        return out
    finally:
        conn.close()
