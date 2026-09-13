"""Estatísticas agregadas pra Dashboard/Sessões/Estatísticas do frontend
— camada fina sobre poker_coach/stats.py, o MESMO módulo usado pelas
páginas Streamlit em app_pages/*.py (home.py, lucro.py, roi.py,
posicao.py, stack.py). Nenhuma lógica nova de agregação aqui, só
serialização — a lógica real mora em stats.py.

Ver docstring de poker_coach.stats: lucro/ROI/ITM/ABI em $ só existem
pra torneios com resultado registrado; o resto (saldo em BB, VPIP/PFR,
horas jogadas) vem 100% da hand history.
"""
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm  # noqa: E402
from poker_coach import stats  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _conn():
    return dbm.connect(DSN)


class RoiOut(BaseModel):
    tournaments: int
    invested: float
    won: float
    profit: float
    roi_pct: float
    itm_pct: float
    abi: float


class OverviewOut(BaseModel):
    hands: int
    tournaments: int
    vpip_pct: float
    pfr_pct: float
    net_bb: float
    hours_played: float
    roi: RoiOut | None  # None = nenhum torneio com resultado registrado ainda


@router.get("/overview", response_model=OverviewOut)
def overview():
    conn = _conn()
    try:
        ov = stats.overview(conn)
        r = stats.roi(conn)
        hours = stats.hours_played(conn)
        return OverviewOut(**ov, hours_played=hours, roi=r)
    finally:
        conn.close()


class PeriodProfitOut(BaseModel):
    period: str
    profit: float
    tournaments: int


@router.get("/profit-by-period", response_model=list[PeriodProfitOut])
def profit_by_period(period: Literal["day", "week", "month"] = Query("day")):
    conn = _conn()
    try:
        return stats.profit_by_period(conn, period)
    finally:
        conn.close()


class DayNetBbOut(BaseModel):
    date: str
    net_bb: float
    hands: int


@router.get("/net-bb-by-day", response_model=list[DayNetBbOut])
def net_bb_by_day():
    conn = _conn()
    try:
        return stats.net_bb_by_day(conn)
    finally:
        conn.close()


class HourNetBbOut(BaseModel):
    hour: int
    net_bb: float
    hands: int


@router.get("/net-bb-by-hour", response_model=list[HourNetBbOut])
def net_bb_by_hour():
    conn = _conn()
    try:
        return stats.net_bb_by_hour(conn)
    finally:
        conn.close()


class WeekdayNetBbOut(BaseModel):
    weekday: str
    net_bb: float
    hands: int


@router.get("/net-bb-by-weekday", response_model=list[WeekdayNetBbOut])
def net_bb_by_weekday():
    conn = _conn()
    try:
        return stats.net_bb_by_weekday(conn)
    finally:
        conn.close()


class BuyinProfitOut(BaseModel):
    buyin: float
    tournaments: int
    profit: float
    roi_pct: float | None
    itm_pct: float | None


@router.get("/profit-by-buyin", response_model=list[BuyinProfitOut])
def profit_by_buyin():
    conn = _conn()
    try:
        return stats.profit_by_buyin(conn)
    finally:
        conn.close()


class PositionStatOut(BaseModel):
    position: str
    spots: int
    vpip_pct: float
    pfr_pct: float
    net_bb: float


@router.get("/position", response_model=list[PositionStatOut])
def position():
    conn = _conn()
    try:
        return stats.position_stats(conn)
    finally:
        conn.close()


class StackBucketOut(BaseModel):
    bucket: str
    spots: int
    fold_pct: float | None
    push_pct: float | None
    call_pct: float | None
    net_bb: float


@router.get("/stack-buckets", response_model=list[StackBucketOut])
def stack_buckets():
    conn = _conn()
    try:
        return stats.stack_bucket_stats(conn)
    finally:
        conn.close()


class CashTicketBucket(BaseModel):
    count: int
    total: float


class CashTicketOut(BaseModel):
    cash: CashTicketBucket
    ticket: CashTicketBucket


@router.get("/cash-vs-ticket", response_model=CashTicketOut)
def cash_vs_ticket():
    conn = _conn()
    try:
        return stats.cash_vs_ticket_summary(conn)
    finally:
        conn.close()


class SatelliteRowOut(BaseModel):
    torneio: str
    site: str
    buyin: float | None
    converteu: str
    valor_estimado: float | None
    nota: str
    data: str | None


class SatellitesOut(BaseModel):
    attempts: int
    converted: int
    pct: float | None
    rows: list[SatelliteRowOut]


@router.get("/satellites", response_model=SatellitesOut)
def satellites():
    conn = _conn()
    try:
        conv = stats.satellite_conversion_rate(conn)
        rows = stats.satellite_history(conn)
        return SatellitesOut(**conv, rows=rows)
    finally:
        conn.close()


class SessionOut(BaseModel):
    date: str
    site: str
    tournaments: int
    hands: int
    duration_min: int
    profit: float | None
    roi_pct: float | None
    abi: float | None
    with_result: int


@router.get("/sessions", response_model=list[SessionOut])
def sessions():
    conn = _conn()
    try:
        return stats.sessions_by_day(conn)
    finally:
        conn.close()
