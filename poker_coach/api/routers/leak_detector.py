"""API do Leak Detector (Fase 3 do plano de RL) — relatório agregado por
categoria de comportamento (over-fold/over-bluff/under-3bet/etc.), preflop
E pós-flop, com sample_size/confidence/EV médio sempre juntos.

Distinto do "Leak Finder" existente (`pushfold.py::leaks`/`leak_hands`),
que é per-hand e escopo estrito de push/fold preflop isolado. Este lê o
dataset exportado pela Fase 1 (`RL_DATASET_PATH`, parquet gerado por
`export-rl`) — snapshot periódico, não live: mesmo espírito da Personal
Policy (recomputa quando `export-rl` roda de novo, não a cada request).
"""
import math
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach.rl import leak_detector as ld  # noqa: E402

from ..deps import RL_DATASET_PATH  # noqa: E402

router = APIRouter(prefix="/api/leak-detector", tags=["leak-detector"])

# Cache em processo, invalidado por mtime do arquivo — mesmo padrão de
# `pushfold.py::_ANALYZE_CACHE`, mas aqui por mtime (o parquet só muda
# quando alguém roda export-rl de novo) em vez de TTL fixo.
_cache: dict = {"mtime": None, "report": None}


def _clean(v):
    """NaN do pandas -> None (JSON não tem NaN de verdade; o frontend
    trata null, não "NaN" solto)."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _load_report():
    if not os.path.exists(RL_DATASET_PATH):
        raise HTTPException(
            404, f"Dataset não encontrado em {RL_DATASET_PATH} — rode "
                 f"'python -m poker_coach.cli export-rl' primeiro."
        )
    mtime = os.path.getmtime(RL_DATASET_PATH)
    if _cache["mtime"] != mtime:
        import pandas as pd
        df = pd.read_parquet(RL_DATASET_PATH)
        _cache["report"] = ld.build_leak_report(df)
        _cache["mtime"] = mtime
    return _cache["report"]


class CategoryRowOut(BaseModel):
    leak_category: str
    sample_size: int
    reference_coverage: float | None
    mean_ev_gap: float | None
    median_ev_gap: float | None
    std_ev_gap: float | None
    confidence: str


class LeakReportOut(BaseModel):
    n_decisions: int
    n_leaks: int
    n_reference_available: int
    sizing_note: str
    by_category: list[CategoryRowOut]


def _row_out(row: dict) -> CategoryRowOut:
    return CategoryRowOut(
        leak_category=row["leak_category"], sample_size=int(row["sample_size"]),
        reference_coverage=_clean(row["reference_coverage"]),
        mean_ev_gap=_clean(row["mean_ev_gap"]), median_ev_gap=_clean(row["median_ev_gap"]),
        std_ev_gap=_clean(row["std_ev_gap"]), confidence=row["confidence"],
    )


@router.get("/report", response_model=LeakReportOut)
def report():
    r = _load_report()
    return LeakReportOut(
        n_decisions=r.n_decisions, n_leaks=r.n_leaks,
        n_reference_available=r.n_reference_available, sizing_note=ld.SIZING_NOTE,
        by_category=[_row_out(row) for row in r.by_category.to_dict("records")],
    )


class BreakdownRowOut(BaseModel):
    leak_category: str
    dimension_value: str | None
    sample_size: int
    reference_coverage: float | None
    mean_ev_gap: float | None
    median_ev_gap: float | None
    std_ev_gap: float | None
    confidence: str


@router.get("/breakdown", response_model=list[BreakdownRowOut])
def breakdown(
    category: str = Query(...),
    dimension: str = Query("position", pattern="^(position|stack)$"),
):
    """"Onde essa categoria mais aparece" (seção 10 do plano) — por
    posição ou por faixa de stack, sempre com sample_size/confidence."""
    r = _load_report()
    df = r.by_category_position if dimension == "position" else r.by_category_stack
    dim_col = "position" if dimension == "position" else "stack_bucket"
    sub = df[df["leak_category"] == category]
    if sub.empty:
        return []
    return [
        BreakdownRowOut(
            leak_category=row["leak_category"], dimension_value=_clean(row[dim_col]),
            sample_size=int(row["sample_size"]), reference_coverage=_clean(row["reference_coverage"]),
            mean_ev_gap=_clean(row["mean_ev_gap"]), median_ev_gap=_clean(row["median_ev_gap"]),
            std_ev_gap=_clean(row["std_ev_gap"]), confidence=row["confidence"],
        )
        for row in sub.to_dict("records")
    ]
