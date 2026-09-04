"""Dependência compartilhada: conexão com o Postgres, uma por request."""
import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm  # noqa: E402

DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach"


def get_conn() -> Iterator[dbm.PGConnection]:
    conn = dbm.connect(DSN)
    try:
        yield conn
    finally:
        conn.close()
