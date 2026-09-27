"""API da tela "Estilo de Jogo" — VPIP, PFR, 3-Bet, Fold to 3-Bet, ATS,
Fold to Steal, C-Bet e Fold to C-Bet do herói, filtráveis por período,
torneio, buy-in, faixa de stack e posição (todos combinados com AND).

Camada fina sobre poker_coach/player_stats.py — toda a lógica (definição
de oportunidade de cada métrica, posição recalculada a partir de
seats + button_seat) mora lá. Toda métrica sai com o denominador (`n` /
`opps`) junto: o frontend nunca recebe um percentual sem a amostra.

Cache em processo da tabela por mão (a parte cara, ~0,5s), invalidado pela
assinatura do banco (COUNT/MAX(ts) de hands) — mesmo espírito do cache por
mtime de `leak_detector.py`: import novo invalida sozinho. Filtros e
agregações rodam sobre o DataFrame em memória (milissegundos).
"""
import datetime as dt
import math
import sys
import threading
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm  # noqa: E402
from poker_coach import player_stats as ps  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/play-style", tags=["play-style"])

_cache: dict = {"signature": None, "df": None}
_lock = threading.Lock()


def _features() -> pd.DataFrame:
    conn = dbm.connect(DSN)
    try:
        sig = ps.data_signature(conn)
        with _lock:
            if _cache["signature"] != sig:
                _cache["df"] = ps.load_hand_features(conn)
                _cache["signature"] = sig
            return _cache["df"]
    finally:
        conn.close()


def _clean(v):
    """NaN/NaT do pandas -> None; numpy -> tipo Python nativo."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
        return None
    if hasattr(v, "item"):
        v = v.item()
        if isinstance(v, float) and math.isnan(v):
            return None
    return v


# ---------------- Opções dos filtros ----------------

class MetricDefOut(BaseModel):
    key: str
    label: str
    description: str


class TournamentOptionOut(BaseModel):
    site: str
    tournament_id: str
    name: str | None
    buyin: float | None
    first_ts: str | None
    hands: int


class OptionsOut(BaseModel):
    buyins: list[float]
    tournaments: list[TournamentOptionOut]
    positions: list[str]            # só as que existem nos dados, em ordem de mesa
    stack_ranges: list[str]
    date_min: str | None
    date_max: str | None
    metrics: list[MetricDefOut]


@router.get("/options", response_model=OptionsOut)
def options():
    df = _features()
    present = set(df["position"].dropna())
    tl = ps.tournament_list(df)
    ts = df["ts"].dropna()
    return OptionsOut(
        buyins=sorted(float(b) for b in df["buyin"].dropna().unique()),
        tournaments=[
            TournamentOptionOut(
                site=r.site, tournament_id=str(r.tournament_id), name=_clean(r.name),
                buyin=_clean(r.buyin),
                first_ts=r.first_ts.isoformat() if pd.notna(r.first_ts) else None,
                hands=int(r.hands),
            )
            for r in tl.itertuples()
        ],
        positions=[p for p in ps.POSITION_ORDER if p in present],
        stack_ranges=ps.STACK_LABELS,
        date_min=ts.min().date().isoformat() if not ts.empty else None,
        date_max=ts.max().date().isoformat() if not ts.empty else None,
        metrics=[MetricDefOut(key=k, label=v[0], description=v[3]) for k, v in ps.METRICS.items()],
    )


# ---------------- Relatório ----------------

class MetricValueOut(BaseModel):
    pct: float | None   # None = nenhuma oportunidade
    made: int
    opps: int


class SummaryOut(BaseModel):
    hands: int
    tournaments: int
    date_min: str | None
    date_max: str | None
    gap: float | None   # VPIP − PFR em pontos percentuais
    vpip: MetricValueOut
    pfr: MetricValueOut
    threebet: MetricValueOut
    f3b: MetricValueOut
    ats: MetricValueOut
    fts: MetricValueOut
    cbet: MetricValueOut
    fcb: MetricValueOut


class GroupRowOut(BaseModel):
    """Uma linha agregada. `<m>` = % (None sem oportunidade), `<m>_n` =
    oportunidades (denominador). VPIP e PFR compartilham o denominador."""
    position: str | None = None
    stack_range: str | None = None
    period: str | None = None
    hands: int
    gap: float | None
    vpip: float | None
    vpip_n: int
    pfr: float | None
    pfr_n: int
    threebet: float | None
    threebet_n: int
    f3b: float | None
    f3b_n: int
    ats: float | None
    ats_n: int
    fts: float | None
    fts_n: int
    cbet: float | None
    cbet_n: int
    fcb: float | None
    fcb_n: int


class ReportOut(BaseModel):
    summary: SummaryOut
    by_stack: list[GroupRowOut]
    by_position: list[GroupRowOut]
    evolution: list[GroupRowOut]
    table: list[GroupRowOut]        # posição × stack


def _rows(by: pd.DataFrame, order_cols: dict[str, list[str]] | None = None) -> list[GroupRowOut]:
    if by.empty:
        return []
    if order_cols:
        keys = [by[c].map({v: i for i, v in enumerate(order)}) for c, order in order_cols.items()]
        by = by.assign(**{f"_o{i}": k for i, k in enumerate(keys)})
        by = by.sort_values([f"_o{i}" for i in range(len(keys))])
    out = []
    for rec in by.to_dict("records"):
        rec = {k: _clean(v) for k, v in rec.items() if not k.startswith("_o")}
        if isinstance(rec.get("period"), (pd.Timestamp, dt.datetime)):
            rec["period"] = rec["period"].date().isoformat()
        out.append(GroupRowOut(**rec))
    return out


@router.get("/report", response_model=ReportOut)
def report(
    period: Literal["all", "today", "7d", "30d", "custom"] = Query("all"),
    date_from: dt.date | None = Query(None, description="Só com period=custom"),
    date_to: dt.date | None = Query(None, description="Só com period=custom"),
    site: str | None = Query(None),
    tournament_id: str | None = Query(None, description="Exige `site`"),
    buyin: float | None = Query(None),
    stack: str | None = Query(None, description="Uma de /options.stack_ranges"),
    position: str | None = Query(None),
    freq: Literal["D", "W", "M"] = Query("W", description="Agrupamento da evolução: dia/semana/mês"),
):
    if stack is not None and stack not in ps.STACK_LABELS:
        raise HTTPException(400, f"stack inválido: {stack!r}")
    if tournament_id is not None and site is None:
        raise HTTPException(400, "tournament_id exige site")
    custom = None
    if period == "custom":
        if date_from is None or date_to is None:
            raise HTTPException(400, "period=custom exige date_from e date_to")
        custom = (date_from, date_to)
    start, end = ps.period_bounds(period, dt.date.today(), custom)

    df = ps.apply_filters(
        _features(), start=start, end=end,
        tournament=(site, tournament_id) if tournament_id is not None else None,
        buyin=buyin, stack=stack, position=position,
    )

    s = ps.summarize(df)
    ts = df["ts"].dropna()
    summary = SummaryOut(
        hands=s["hands"],
        tournaments=int(df[["site", "tournament_id"]].drop_duplicates().shape[0]),
        date_min=ts.min().isoformat() if not ts.empty else None,
        date_max=ts.max().isoformat() if not ts.empty else None,
        gap=s["gap"],
        **{k: MetricValueOut(**s[k]) for k in ps.METRICS},
    )
    return ReportOut(
        summary=summary,
        by_stack=_rows(ps.summarize_by(df, ["stack_range"]), {"stack_range": ps.STACK_LABELS}),
        by_position=_rows(ps.summarize_by(df, ["position"]), {"position": ps.POSITION_ORDER}),
        evolution=_rows(ps.evolution(df, freq)),
        table=_rows(ps.summarize_by(df, ["position", "stack_range"]),
                    {"position": ps.POSITION_ORDER, "stack_range": ps.STACK_LABELS}),
    )
