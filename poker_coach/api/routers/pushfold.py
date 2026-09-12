"""Push/Fold: relatório em lote, grid de range, e o treinador (Modo Estudo).

Escopo do motor (poker_coach/pushfold): decisões heads-up simples —
ABERTURA preflop (herói é o primeiro a agir voluntariamente, ninguém
entrou antes; vilão modelado = a BB) e, no treinador, também "facing
shove" (um vilão só deu all-in antes do herói decidir, sem ninguém
pelo meio além de folds). Squeeze/multiway/3-bet e qualquer coisa
pós-flop não são julgados aqui. Chip EV, não ICM (ver /icm).
"""
import sys
import time
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from poker_coach import db as dbm  # noqa: E402
from poker_coach.models import Hand as HandModel, Seat  # noqa: E402
from poker_coach.pushfold import analyze as pf  # noqa: E402
from poker_coach.pushfold import equity as eq  # noqa: E402
from poker_coach.pushfold import nash  # noqa: E402

from ..deps import DSN  # noqa: E402

router = APIRouter(prefix="/api/pushfold", tags=["pushfold"])

# ── Cache de processo para analyze_all ──────────────────────────────────────
# Evita rodar o solver duas vezes quando /spots e /summary são chamados
# em paralelo (o que o frontend faz na mesma página).
_ANALYZE_CACHE: dict[tuple, tuple[float, list]] = {}
_CACHE_TTL = 300  # segundos (5 min) — invalida automaticamente após importação nova


def _get_analysis(bb_min: float, bb_max: float) -> list:
    """Retorna o resultado de analyze_all, usando cache de processo com TTL."""
    key = (round(bb_min, 2), round(bb_max, 2))
    entry = _ANALYZE_CACHE.get(key)
    if entry:
        cached_at, rows = entry
        if time.monotonic() - cached_at < _CACHE_TTL:
            return rows
    conn = _conn()
    try:
        rows = pf.analyze_all(conn, bb_min=bb_min, bb_max=bb_max)
    finally:
        conn.close()
    _ANALYZE_CACHE[key] = (time.monotonic(), rows)
    return rows


def _conn():
    return dbm.connect(DSN)


class SpotOut(BaseModel):
    site: str
    hand_id: str
    tournament_id: str
    spot: str  # descrição templada, ex. "Abertura (BTN)"
    position: str
    stack: str  # "14.2 BB"
    hero_cards: str
    taken: Literal["Fold", "All-in"]
    correct: Literal["Fold", "All-in"]
    ev: float  # EV do push (BB) contra a range de call de equilíbrio
    ev_lost_bb: float  # 0 se a decisão bateu com o Nash


def _to_spot_out(r: pf.LeakRow) -> SpotOut:
    return SpotOut(
        site=r.site, hand_id=r.hand_id, tournament_id=r.tournament_id,
        spot=f"Abertura ({r.position})", position=r.position,
        stack=f"{r.effective_bb} BB", hero_cards=r.hero_cards,
        taken="All-in" if r.hero_decision == "push" else "Fold",
        correct="All-in" if r.nash_decision == "push" else "Fold",
        ev=r.ev_push_bb, ev_lost_bb=r.ev_lost_bb,
    )


@router.get("/spots", response_model=list[SpotOut])
def list_spots(bb_min: float = Query(5.0), bb_max: float = Query(25.0),
               limit: int | None = Query(None)):
    rows = _get_analysis(bb_min, bb_max)
    if limit is not None:
        rows = rows[:limit]
    return [_to_spot_out(r) for r in rows]


class SummaryOut(BaseModel):
    spots: int
    leak_spots: int
    total_ev_lost_bb: float
    by_position: dict


@router.get("/summary", response_model=SummaryOut)
def summary(bb_min: float = Query(5.0), bb_max: float = Query(25.0)):
    rows = _get_analysis(bb_min, bb_max)
    s = pf.summarize(rows)
    return SummaryOut(spots=s["spots"], leak_spots=s["leak_spots"],
                      total_ev_lost_bb=s["total_ev_lost_bb"], by_position=s["by_position"])


class RangeGridOut(BaseModel):
    effective_bb: float
    pot_bb: float
    shove_pct: float
    call_pct: float
    grid: dict[str, float]  # classe da mão -> EV do push (BB)


@router.get("/range-grid", response_model=RangeGridOut)
def range_grid(effective_bb: float = Query(10.0, gt=0), pot_bb: float = Query(1.5, gt=0)):
    grid, result = nash.ev_grid(effective_bb, pot_bb)
    return RangeGridOut(effective_bb=effective_bb, pot_bb=pot_bb,
                         shove_pct=result.shove_pct, call_pct=result.call_pct, grid=grid)


@router.get("/call-grid", response_model=RangeGridOut)
def call_grid(effective_bb: float = Query(10.0, gt=0), pot_bb: float = Query(1.5, gt=0)):
    """Espelho de /range-grid pro lado de quem PAGA um all-in (mode
    'facing_shove' do treinador): EV de cada classe pagando a range de
    shove de equilíbrio do vilão nesse stack/pot. `shove_pct`/`call_pct`
    no retorno continuam sendo os do vilão (pra manter o mesmo shape do
    /range-grid); o grid em si é que muda de EV do push pra EV do call."""
    grid, result = nash.call_ev_grid(effective_bb, pot_bb)
    return RangeGridOut(effective_bb=effective_bb, pot_bb=pot_bb,
                         shove_pct=result.shove_pct, call_pct=result.call_pct, grid=grid)


# ---------------- Treinador (Modo Estudo) ----------------

class TrainerSeatOut(BaseModel):
    position: str
    is_hero: bool
    stack: int


class TrainerQuestionOut(BaseModel):
    site: str
    hand_id: str
    mode: Literal["open", "facing_shove"] = "open"
    hero_cards: str
    position: str
    shover_position: str | None = None  # só em mode="facing_shove"
    effective_bb: float
    pot_bb: float
    n_players: int
    bb: int  # tamanho do big blind (chips) — pra desenhar o stack de cada assento em BB
    seats: list[TrainerSeatOut]
    context: str  # texto templado


def _seats_for_hand(conn, site: str, hand_id: str, hero: str) -> tuple[list[TrainerSeatOut], int, int]:
    """Assentos (só posição/stack, pra desenhar a mesa) — reusa
    Hand.position_order() com um Hand "stub" (mesmo padrão de
    pushfold/analyze.py e icm_analyze.py)."""
    row = conn.execute("SELECT button_seat, bb FROM hands WHERE site=? AND hand_id=?",
                        (site, hand_id)).fetchone()
    button_seat, bb = row
    seats = [Seat(seat_no, player, stack) for seat_no, player, stack in conn.execute(
        "SELECT seat_no, player, stack FROM seats WHERE site=? AND hand_id=?", (site, hand_id))]
    stub = HandModel(site="", hand_id="", tournament_id="", timestamp=None, level=None,
                      sb=0, bb=bb, ante=0, buyin=None, currency=None, table_name=None,
                      max_players=None, button_seat=button_seat, seats=seats)
    order = stub.position_order() or []
    out = [TrainerSeatOut(position=label, is_hero=(seat.player == hero), stack=seat.stack)
           for label, seat in order]
    return out, len(seats), bb


@router.get("/trainer/next", response_model=TrainerQuestionOut)
def trainer_next(
    mode: Literal["open", "facing_shove"] = Query(
        "open", description="'open': herói é o primeiro a agir. 'facing_shove': um "
                             "vilão já deu all-in antes do herói decidir."),
    bb_min: float = Query(5.0, ge=1, description="Proxy de fase do torneio: stack raso = final/bolha, fundo = início"),
    bb_max: float = Query(25.0, le=100),
    n_players: int | None = Query(None, ge=2, le=9, description="Filtra por jogadores na mesa (None = qualquer)"),
):
    conn = _conn()
    try:
        where = ["hero_position IS NOT NULL", "hero_stack_bb BETWEEN ? AND ?"]
        params: list = [bb_min, bb_max]
        if mode == "open":
            where.append("hero_position != 'BB'")
        if n_players is not None:
            where.append("n_players = ?")
            params.append(n_players)
        candidates = conn.execute(
            f"SELECT site, hand_id, hero FROM hands WHERE {' AND '.join(where)} "
            f"ORDER BY RANDOM() LIMIT 60",
            params,
        ).fetchall()
        for site, hand_id, hero in candidates:
            if mode == "open":
                row = pf.analyze_hand_row(conn, site, hand_id, precise=False)
                if row is not None:
                    seats, np_, bb = _seats_for_hand(conn, site, hand_id, hero)
                    return TrainerQuestionOut(
                        site=row.site, hand_id=row.hand_id, mode="open",
                        hero_cards=row.hero_cards,
                        position=row.position, effective_bb=row.effective_bb, pot_bb=row.pot_bb,
                        n_players=np_, bb=bb, seats=seats,
                        context=f"Ninguém entrou no pote ainda. Você é {row.position} "
                                f"com {row.effective_bb} BB efetivos.",
                    )
            else:
                frow = pf.analyze_facing_shove_hand_row(conn, site, hand_id, precise=False)
                if frow is not None:
                    seats, np_, bb = _seats_for_hand(conn, site, hand_id, hero)
                    return TrainerQuestionOut(
                        site=frow.site, hand_id=frow.hand_id, mode="facing_shove",
                        hero_cards=frow.hero_cards, position=frow.position,
                        shover_position=frow.shover_position,
                        effective_bb=frow.effective_bb, pot_bb=frow.pot_bb,
                        n_players=np_, bb=bb, seats=seats,
                        context=f"{frow.shover_position} deu all-in antes de você agir. "
                                f"Você é {frow.position} com {frow.effective_bb} BB efetivos.",
                    )
        raise HTTPException(
            404, f"Nenhum spot {'de abertura' if mode == 'open' else 'de all-in antes de você'} "
                 f"disponível ({bb_min}-{bb_max} BB{f', {n_players} jogadores' if n_players else ''})."
        )
    finally:
        conn.close()


DIVERSE_HAND_POOL = [
    "Ah Kd", "7s 6s", "Qc Jc", "2h 2d", "As 5s",
    "Kh Td", "9c 8c", "8s 8h", "Qs Jd", "Ac 4c",
    "Jh Ts", "6d 5d", "Kc Qs", "5c 5h", "Ad 9d"
]


@router.get("/trainer/next-same-scenario", response_model=list[TrainerQuestionOut])
def trainer_next_same_scenario(
    mode: Literal["open", "facing_shove"] = Query(
        "open", description="'open': herói é o primeiro a agir. 'facing_shove': um "
                             "vilão já deu all-in antes do herói decidir."),
    bb_min: float = Query(5.0, ge=1, description="Proxy de fase do torneio"),
    bb_max: float = Query(25.0, le=100),
    n_players: int | None = Query(None, ge=2, le=9, description="Filtra por jogadores na mesa"),
    count: int = Query(4, ge=1, le=10, description="Quantidade de mãos no mesmo cenário"),
):
    conn = _conn()
    try:
        where = ["hero_position IS NOT NULL", "hero_stack_bb BETWEEN ? AND ?"]
        params: list = [bb_min, bb_max]
        if mode == "open":
            where.append("hero_position != 'BB'")
        if n_players is not None:
            where.append("n_players = ?")
            params.append(n_players)
        candidates = conn.execute(
            f"SELECT site, hand_id, hero FROM hands WHERE {' AND '.join(where)} "
            f"ORDER BY RANDOM() LIMIT 60",
            params,
        ).fetchall()
        for site, hand_id, hero in candidates:
            base_q = None
            if mode == "open":
                row = pf.analyze_hand_row(conn, site, hand_id, precise=False)
                if row is not None:
                    seats, np_, bb = _seats_for_hand(conn, site, hand_id, hero)
                    base_q = TrainerQuestionOut(
                        site=row.site, hand_id=row.hand_id, mode="open",
                        hero_cards=row.hero_cards,
                        position=row.position, effective_bb=row.effective_bb, pot_bb=row.pot_bb,
                        n_players=np_, bb=bb, seats=seats,
                        context=f"Ninguém entrou no pote ainda. Você é {row.position} "
                                f"com {row.effective_bb} BB efetivos.",
                    )
            else:
                frow = pf.analyze_facing_shove_hand_row(conn, site, hand_id, precise=False)
                if frow is not None:
                    seats, np_, bb = _seats_for_hand(conn, site, hand_id, hero)
                    base_q = TrainerQuestionOut(
                        site=frow.site, hand_id=frow.hand_id, mode="facing_shove",
                        hero_cards=frow.hero_cards, position=frow.position,
                        shover_position=frow.shover_position,
                        effective_bb=frow.effective_bb, pot_bb=frow.pot_bb,
                        n_players=np_, bb=bb, seats=seats,
                        context=f"{frow.shover_position} deu all-in antes de você agir. "
                                f"Você é {frow.position} com {frow.effective_bb} BB efetivos.",
                    )
            if base_q is not None:
                chosen_cards: list[str] = [base_q.hero_cards]
                other_hands = conn.execute(
                    "SELECT hero_cards FROM hands WHERE hero_position = ? AND hero_stack_bb BETWEEN ? AND ? AND hero_cards IS NOT NULL AND site = ?",
                    (base_q.position, max(1.0, base_q.effective_bb - 3.0), base_q.effective_bb + 3.0, base_q.site)
                ).fetchall()
                for (hc,) in other_hands:
                    if hc and hc not in chosen_cards:
                        chosen_cards.append(hc)
                        if len(chosen_cards) >= count:
                            break
                if len(chosen_cards) < count:
                    for dh in DIVERSE_HAND_POOL:
                        if dh not in chosen_cards:
                            chosen_cards.append(dh)
                            if len(chosen_cards) >= count:
                                break
                out: list[TrainerQuestionOut] = []
                for hc in chosen_cards[:count]:
                    q_copy = base_q.model_copy()
                    q_copy.hero_cards = hc
                    out.append(q_copy)
                return out

        raise HTTPException(
            404, f"Nenhum spot {'de abertura' if mode == 'open' else 'de all-in antes de você'} "
                 f"disponível ({bb_min}-{bb_max} BB{f', {n_players} jogadores' if n_players else ''})."
        )
    finally:
        conn.close()


class TrainerAnswerIn(BaseModel):
    site: str
    hand_id: str
    mode: Literal["open", "facing_shove"] = "open"
    decision: Literal["Fold", "All-in", "Call"]
    hero_cards: str | None = None


class TrainerAnswerOut(BaseModel):
    correct: bool
    nash_decision: Literal["Fold", "All-in", "Call"]
    ev_bb: float
    ev_lost_bb: float
    explanation: str  # templado a partir dos números, não é prosa gerada por IA


@router.post("/trainer/answer", response_model=TrainerAnswerOut)
def trainer_answer(payload: TrainerAnswerIn):
    conn = _conn()
    try:
        if payload.mode == "open":
            row = pf.analyze_hand_row(conn, payload.site, payload.hand_id, precise=False)
            if row is None:
                raise HTTPException(404, "Mão fora do escopo do motor (não é mais um spot de abertura).")
            hero_cards = payload.hero_cards or row.hero_cards
            if payload.hero_cards and payload.hero_cards != row.hero_cards:
                result = pf._cached_solve(round(row.effective_bb * 2) / 2, round(row.pot_bb * 4) / 4)
                hcls = eq.class_of(eq.parse_hand(hero_cards))
                equity_vs_range = eq.equity_class_vs_range(hcls, result.call_classes, pf._matrix())
                call_pct = result.call_pct / 100  # result.call_pct é 0..100, não 0..1
                p_fold = 1 - call_pct
                ev_push_bb = round(p_fold * row.pot_bb + call_pct * (equity_vs_range * (row.pot_bb + 2 * row.effective_bb) - row.effective_bb), 2)
                nash_label: Literal["Fold", "All-in", "Call"] = "All-in" if ev_push_bb > 0 else "Fold"
                correct = payload.decision == nash_label
                ev_lost = 0.0 if correct else abs(ev_push_bb if nash_label == "All-in" else -ev_push_bb)
                dbm.log_quiz_answer(conn, payload.site, payload.hand_id,
                                     "push" if payload.decision == "All-in" else "fold",
                                     "push" if nash_label == "All-in" else "fold", ev_lost)
                conn.commit()
                if nash_label == "All-in":
                    explanation = (f"Nash manda empurrar: EV do push é {ev_push_bb:+.2f} BB "
                                    f"contra a range de call de equilíbrio da BB nesse stack/pot.")
                else:
                    explanation = (f"Nash manda foldar: o push teria EV {ev_push_bb:+.2f} BB "
                                    f"(negativo) contra a range de call da BB.")
                return TrainerAnswerOut(correct=correct, nash_decision=nash_label,
                                         ev_bb=ev_push_bb, ev_lost_bb=ev_lost,
                                         explanation=explanation)

            nash_label: Literal["Fold", "All-in", "Call"] = (
                "All-in" if row.nash_decision == "push" else "Fold")
            correct = payload.decision == nash_label
            ev_lost = 0.0 if correct else abs(row.ev_push_bb if row.nash_decision == "push" else -row.ev_push_bb)
            dbm.log_quiz_answer(conn, payload.site, payload.hand_id,
                                 "push" if payload.decision == "All-in" else "fold",
                                 row.nash_decision, ev_lost)
            conn.commit()
            if nash_label == "All-in":
                explanation = (f"Nash manda empurrar: EV do push é {row.ev_push_bb:+.2f} BB "
                                f"contra a range de call de equilíbrio da BB nesse stack/pot.")
            else:
                explanation = (f"Nash manda foldar: o push teria EV {row.ev_push_bb:+.2f} BB "
                                f"(negativo) contra a range de call da BB.")
            return TrainerAnswerOut(correct=correct, nash_decision=nash_label,
                                     ev_bb=row.ev_push_bb, ev_lost_bb=ev_lost,
                                     explanation=explanation)

        frow = pf.analyze_facing_shove_hand_row(conn, payload.site, payload.hand_id, precise=False)
        if frow is None:
            raise HTTPException(
                404, "Mão fora do escopo do motor (não é mais um spot de all-in antes de você).")
        hero_cards = payload.hero_cards or frow.hero_cards
        if payload.hero_cards and payload.hero_cards != frow.hero_cards:
            result = pf._cached_solve(round(frow.effective_bb * 2) / 2, round(frow.pot_bb * 4) / 4)
            hcls = eq.class_of(eq.parse_hand(hero_cards))
            equity_vs_range = eq.equity_class_vs_range(hcls, result.shove_classes, pf._matrix())
            ev_call_bb = round(equity_vs_range * (frow.pot_bb + 2 * frow.effective_bb) - frow.effective_bb, 2)
            nash_label = "Call" if ev_call_bb > 0 else "Fold"
            correct = payload.decision == nash_label
            ev_lost = 0.0 if correct else abs(ev_call_bb if nash_label == "Call" else -ev_call_bb)
            dbm.log_quiz_answer(conn, payload.site, payload.hand_id,
                                 "call" if payload.decision == "Call" else "fold",
                                 "call" if nash_label == "Call" else "fold", ev_lost)
            conn.commit()
            if nash_label == "Call":
                explanation = (f"Nash manda pagar: EV do call é {ev_call_bb:+.2f} BB contra a "
                                f"range de all-in de equilíbrio de {frow.shover_position} nesse "
                                f"stack/pot.")
            else:
                explanation = (f"Nash manda foldar: o call teria EV {ev_call_bb:+.2f} BB "
                                f"(negativo) contra a range de all-in de {frow.shover_position}.")
            return TrainerAnswerOut(correct=correct, nash_decision=nash_label,
                                     ev_bb=ev_call_bb, ev_lost_bb=ev_lost, explanation=explanation)

        nash_label = "Call" if frow.nash_decision == "call" else "Fold"
        correct = payload.decision == nash_label
        ev_lost = 0.0 if correct else abs(frow.ev_call_bb if frow.nash_decision == "call" else -frow.ev_call_bb)
        dbm.log_quiz_answer(conn, payload.site, payload.hand_id,
                             "call" if payload.decision == "Call" else "fold",
                             frow.nash_decision, ev_lost)
        conn.commit()
        if nash_label == "Call":
            explanation = (f"Nash manda pagar: EV do call é {frow.ev_call_bb:+.2f} BB contra a "
                            f"range de all-in de equilíbrio de {frow.shover_position} nesse "
                            f"stack/pot.")
        else:
            explanation = (f"Nash manda foldar: o call teria EV {frow.ev_call_bb:+.2f} BB "
                            f"(negativo) contra a range de all-in de {frow.shover_position}.")
        return TrainerAnswerOut(correct=correct, nash_decision=nash_label,
                                 ev_bb=frow.ev_call_bb, ev_lost_bb=ev_lost, explanation=explanation)
    finally:
        conn.close()


class TrainerStatsOut(BaseModel):
    total: int
    correct: int
    pct: float | None



@router.get("/trainer/stats", response_model=TrainerStatsOut)
def trainer_stats():
    conn = _conn()
    try:
        return TrainerStatsOut(**dbm.quiz_stats(conn))
    finally:
        conn.close()
