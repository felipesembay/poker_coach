"""ICM: exige premiação salva + confirmação explícita de mesa final antes
de calcular qualquer coisa (ver poker_coach/icm.py — a hand history só
mostra sua mesa, nunca o campo inteiro do torneio).

`category` (Mesa Final/Bolha/Satélite) é HEURÍSTICA, derivada de
payouts x jogadores restantes — não uma classificação real do motor.
"Hero Call" do mock não existe aqui: análise pós-flop não é coberta.
`risk` é um bucket arbitrário sobre risk_premium_pct (thresholds em
poker_coach.icm, documentados, não uma escala padrão da indústria).
"""
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm  # noqa: E402
from poker_coach import icm_analyze as ia  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/icm", tags=["icm"])


def _conn():
    return dbm.connect(DSN)


class TournamentOut(BaseModel):
    site: str
    tournament_id: str
    name: str | None
    buyin: float | None
    has_payouts: bool


@router.get("/tournaments", response_model=list[TournamentOut])
def list_tournaments():
    conn = _conn()
    try:
        rows = conn.execute(
            """SELECT t.site, t.tournament_id, t.name, t.buyin,
                      EXISTS(SELECT 1 FROM payouts p WHERE p.site=t.site
                             AND p.tournament_id=t.tournament_id) AS has_payouts
               FROM tournaments t
               WHERE t.tournament_id IN (SELECT DISTINCT tournament_id FROM hands)
               ORDER BY t.first_seen DESC"""
        ).fetchall()
        return [TournamentOut(site=s, tournament_id=tid, name=n, buyin=b, has_payouts=hp)
                for s, tid, n, b, hp in rows]
    finally:
        conn.close()


class PayoutsIn(BaseModel):
    prizes: list[float]  # [1º lugar, 2º, 3º, ...]


@router.get("/tournaments/{site}/{tournament_id}/payouts", response_model=list[float])
def get_payouts(site: str, tournament_id: str):
    conn = _conn()
    try:
        return dbm.get_payouts(conn, site, tournament_id)
    finally:
        conn.close()


@router.put("/tournaments/{site}/{tournament_id}/payouts")
def set_payouts(site: str, tournament_id: str, payload: PayoutsIn):
    conn = _conn()
    try:
        dbm.set_payouts(conn, site, tournament_id, payload.prizes)
        conn.commit()
        return {"ok": True, "prizes": payload.prizes}
    finally:
        conn.close()


def _category(n_players: int, payouts: list[float]) -> str:
    paid = [p for p in payouts if p > 0]
    if n_players > len(paid):
        return "Bolha"
    if paid and max(paid) - min(paid) < 1e-6:
        return "Satélite"
    return "Mesa Final"


def _risk_bucket(pct: float) -> str:
    a = abs(pct)
    if a < 5:
        return "Baixo"
    if a < 15:
        return "Médio"
    if a < 30:
        return "Alto"
    return "Extremo" if a >= 45 else "Crítico"


class IcmSpotOut(BaseModel):
    site: str
    hand_id: str
    tournament_id: str
    scenario: str
    category: Literal["Mesa Final", "Bolha", "Satélite"]
    stack: str
    risk: str
    risk_premium_pct: float
    hero_decision: Literal["push", "fold"]
    icm_decision: Literal["push", "fold"]
    icm_ev_fold: float
    icm_ev_push: float
    ev_diff: float
    icm_ev_lost: float


class IcmSummaryOut(BaseModel):
    spots: int
    leak_spots: int
    total_ev_lost: float
    rows: list[IcmSpotOut]


@router.get("/spots", response_model=IcmSummaryOut)
def icm_spots(site: str = Query(...), tournament_id: str = Query(...),
               max_table_size: int = Query(9, ge=2, le=9),
               confirmed: bool = Query(False)):
    if not confirmed:
        raise HTTPException(
            400,
            "Confirmação obrigatória: passe confirmed=true só depois do usuário "
            "confirmar explicitamente que essas mãos são de mesa final. A hand "
            "history não mostra o campo inteiro do torneio — sem essa confirmação "
            "o número seria inventado."
        )
    conn = _conn()
    try:
        payouts = dbm.get_payouts(conn, site, tournament_id)
        if not payouts:
            raise HTTPException(400, "Torneio sem estrutura de premiação salva "
                                 "(PUT /api/icm/tournaments/{site}/{tournament_id}/payouts primeiro).")
        rows = ia.analyze_icm_tournament(conn, site, tournament_id, payouts,
                                          max_table_size=max_table_size)
        out = []
        for r in rows:
            out.append(IcmSpotOut(
                site=r.site, hand_id=r.hand_id, tournament_id=r.tournament_id,
                scenario=f"{r.n_players}-handed, {r.position} abre",
                category=_category(r.n_players, payouts),  # type: ignore[arg-type]
                stack=f"{r.effective_bb} BB", risk=_risk_bucket(r.risk_premium_pct),
                risk_premium_pct=r.risk_premium_pct,
                hero_decision=r.hero_decision, icm_decision=r.icm_decision,
                icm_ev_fold=r.icm_ev_fold, icm_ev_push=r.icm_ev_push,
                ev_diff=round(r.icm_ev_push - r.icm_ev_fold, 2), icm_ev_lost=r.icm_ev_lost,
            ))
        s = ia.summarize_icm(rows)
        return IcmSummaryOut(spots=s["spots"], leak_spots=s["leak_spots"],
                              total_ev_lost=s["total_ev_lost"], rows=out)
    finally:
        conn.close()


class IcmHandOut(BaseModel):
    in_scope: bool
    reason: str | None = None
    hero_decision: Literal["push", "fold"] | None = None
    icm_decision: Literal["push", "fold"] | None = None
    icm_ev_fold: float | None = None
    icm_ev_push: float | None = None
    icm_ev_lost: float | None = None
    risk_premium_pct: float | None = None
    effective_bb: float | None = None


@router.get("/hand/{site}/{hand_id}", response_model=IcmHandOut)
def icm_hand(site: str, hand_id: str, confirmed: bool = Query(False)):
    """Mesmo motor de `/spots`, só que pra uma mão só — pensado pro
    Replayer perguntar "essa jogada preflop foi a mais assertiva pelo
    ICM?" sem precisar rodar o torneio inteiro antes."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT tournament_id FROM hands WHERE site=? AND hand_id=?", (site, hand_id)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Mão não encontrada.")
        tournament_id = row[0]

        if not confirmed:
            return IcmHandOut(
                in_scope=False,
                reason="Confirmação obrigatória: ICM só faz sentido com o campo "
                       "inteiro do torneio (mesa final/bolha). Confirme que essa "
                       "mão é desse cenário pra calcular (confirmed=true).",
            )
        payouts = dbm.get_payouts(conn, site, tournament_id)
        if not payouts:
            return IcmHandOut(
                in_scope=False,
                reason="Torneio sem premiação salva. Cadastre em ICM → Torneio "
                       "antes de calcular.",
            )
        r = ia.analyze_icm_hand_row(conn, site, hand_id, payouts)
        if r is None:
            return IcmHandOut(
                in_scope=False,
                reason="Spot fora do escopo do motor de ICM (só cobre a abertura "
                       "preflop do Hero contra o BB, sem ninguém ter entrado antes, "
                       "e stack efetivo entre 1 e 40 BB).",
            )
        return IcmHandOut(
            in_scope=True, hero_decision=r.hero_decision, icm_decision=r.icm_decision,
            icm_ev_fold=r.icm_ev_fold, icm_ev_push=r.icm_ev_push,
            icm_ev_lost=r.icm_ev_lost, risk_premium_pct=r.risk_premium_pct,
            effective_bb=r.effective_bb,
        )
    finally:
        conn.close()
