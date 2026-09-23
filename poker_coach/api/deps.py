"""Dependência compartilhada: conexão com o Postgres, uma por request."""
import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm  # noqa: E402

DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach"

# Artefato da Personal Policy (Fase 2 do plano de RL, Behavioral Cloning
# — poker_coach/poker_coach/rl/personal_policy.py). Opcional: se o arquivo
# não existir, o endpoint que usa isso (trainer/answer) simplesmente não
# inclui a comparação — não quebra por falta de modelo (seção 18 do plano).
PERSONAL_POLICY_PATH = str(
    Path(__file__).resolve().parents[2] / "datasets" / "personal_policy.pkl"
)


def get_conn() -> Iterator[dbm.PGConnection]:
    conn = dbm.connect(DSN)
    try:
        yield conn
    finally:
        conn.close()
