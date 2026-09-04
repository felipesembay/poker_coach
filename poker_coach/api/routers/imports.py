"""Importação de hand history via upload (multipart) — mesma lógica do
CLI (`poker_coach.cli`) e da página de Configuração do Streamlit, só
que exposta como endpoint HTTP pro frontend React.
"""
import sys
from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm  # noqa: E402
from poker_coach.cli import detect_site  # noqa: E402
from poker_coach.parsers import partypoker, pokerstars  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/import", tags=["import"])


class FileResult(BaseModel):
    filename: str
    site: str | None
    hands_in_file: int
    hands_new: int
    error: str | None = None


class ImportResult(BaseModel):
    files: list[FileResult]
    total_new: int


@router.post("", response_model=ImportResult)
async def import_hand_histories(files: list[UploadFile] = File(...)):
    conn = dbm.connect(DSN)
    results: list[FileResult] = []
    total_new = 0
    try:
        for f in files:
            raw = await f.read()
            text = raw.decode("utf-8", errors="replace")
            site = detect_site(text)
            if site is None:
                results.append(FileResult(
                    filename=f.filename or "?", site=None, hands_in_file=0,
                    hands_new=0, error="Formato não reconhecido (nem PartyPoker nem PokerStars).",
                ))
                continue
            parser = pokerstars if site == "pokerstars" else partypoker
            hands = parser.parse_file(text)
            new = sum(dbm.insert_hand(conn, h) for h in hands)
            conn.commit()
            total_new += new
            results.append(FileResult(
                filename=f.filename or "?", site=site,
                hands_in_file=len(hands), hands_new=new,
            ))
        return ImportResult(files=results, total_new=total_new)
    finally:
        conn.close()
