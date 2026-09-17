"""Estatísticas do Decision Engine (Etapa 7) — camada fina sobre
poker_coach/decision_stats.py, que lê a tabela decision_analysis
(preenchida opcionalmente via GET /api/replayer/{site}/{hand_id}/
decision/{step}?persist=true). Sem dado nenhum aqui até o usuário
persistir análises pelo Replayer — n=0 em tudo é o estado inicial normal,
não um bug.
"""
import sys
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm  # noqa: E402
from poker_coach import decision_stats  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/decision-stats", tags=["decision-stats"])


def _conn():
    return dbm.connect(DSN)


class PreflopModelPerformanceOut(BaseModel):
    n: int
    avg_ev_theoretical_bb: float | None
    avg_actual_result_bb: float | None
    error_rate_pct: float | None
    avg_ev_lost_on_error_bb: float | None


class ContextualDecisionPerformanceOut(BaseModel):
    n: int
    avg_hero_equity_pct: float | None
    avg_required_equity_pct: float | None
    avg_ev_call_bb: float | None
    avg_ev_fold_bb: float | None
    avg_ev_push_bb: float | None
    error_rate_pct: float | None
    avg_actual_result_bb: float | None


class ByStreetOut(BaseModel):
    street: str
    n: int
    avg_hero_equity_pct: float | None
    avg_ev_call_bb: float | None
    avg_required_equity_pct: float | None
    avg_actual_result_bb: float | None


class ByPositionOut(BaseModel):
    position: str
    n: int
    avg_hero_equity_pct: float | None
    avg_actual_result_bb: float | None


class ByStackOut(BaseModel):
    bucket: str
    n: int
    avg_hero_equity_pct: float | None
    avg_actual_result_bb: float | None


class ByTextureOut(BaseModel):
    texture: str
    n: int
    avg_hero_equity_pct: float | None
    avg_actual_result_bb: float | None


class PostflopPerformanceOut(BaseModel):
    by_street: list[ByStreetOut]
    by_position: list[ByPositionOut]
    by_stack: list[ByStackOut]
    by_texture: list[ByTextureOut]


@router.get("/preflop", response_model=PreflopModelPerformanceOut)
def preflop_model_performance():
    conn = _conn()
    try:
        return decision_stats.preflop_model_performance(conn)
    finally:
        conn.close()


@router.get("/contextual", response_model=ContextualDecisionPerformanceOut)
def contextual_decision_performance():
    conn = _conn()
    try:
        return decision_stats.contextual_decision_performance(conn)
    finally:
        conn.close()


@router.get("/postflop", response_model=PostflopPerformanceOut)
def postflop_performance():
    conn = _conn()
    try:
        return decision_stats.postflop_performance(conn)
    finally:
        conn.close()
