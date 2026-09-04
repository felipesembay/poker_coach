"""Tags: listagem com contagem. `color` é heurística por palavra-chave
(não é um dado armazenado) — ver _color() abaixo."""
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/tags", tags=["tags"])

_LOSS_WORDS = {"cooler", "bad beat", "bluff caught"}
_PROFIT_WORDS = {"value", "steal", "hero call"}


def _color(tag: str) -> str:
    low = tag.lower()
    if low in _LOSS_WORDS:
        return "loss"
    if low in _PROFIT_WORDS:
        return "profit"
    return "primary"


class TagOut(BaseModel):
    name: str
    count: int
    color: str


@router.get("", response_model=list[TagOut])
def list_tags():
    conn = dbm.connect(DSN)
    try:
        rows = conn.execute(
            "SELECT tag, COUNT(*) FROM tags GROUP BY tag ORDER BY COUNT(*) DESC"
        ).fetchall()
        return [TagOut(name=t, count=c, color=_color(t)) for t, c in rows]
    finally:
        conn.close()
