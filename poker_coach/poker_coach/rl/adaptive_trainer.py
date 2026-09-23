"""Adaptive Trainer (seção 19 do plano) — sessão de treino interativa
sobre spots de push/fold, histórico real ou sintético.

Motor/engine SÓ — sem UI (fica pra depois, pedido explícito do usuário).
Uso agora: CLI (`python -m poker_coach.cli adaptive-trainer`).

Fluxo: seleciona um spot -> pergunta "o que você faz?" (push/fold) ->
devolve sua ação, a ação da Personal Policy (Fase 2, se um modelo
treinado for passado), a ação de Referência (Nash, motor já existente),
EV(sua ação), EV(referência), EV_gap -> loga a sessão em
`adaptive_trainer_log` (permite medir evolução ao longo do tempo depois,
via `db.adaptive_trainer_stats`).

Reaproveita: `pushfold.analyze._cached_solve` (mesmo cache do resto do
app), `pushfold.nash.ev_grid`, `pushfold.equity.build_ranking`/
`class_representative`/`class_of`, `handeval.parse_hand`/`hand_str` — não
reimplementa equilíbrio nem parsing de carta."""
from __future__ import annotations

import random
from dataclasses import dataclass

from .. import db as dbm
from ..handeval import hand_str, parse_hand
from ..pushfold import analyze as pf_analyze
from ..pushfold import equity as pf_equity
from ..pushfold import nash as pf_nash
from .pushfold_env import _round_for_cache


@dataclass
class TrainingSituation:
    source: str  # "historical" | "synthetic"
    site: str | None
    hand_id: str | None
    position: str | None
    hero_cards: str
    hand_class: str
    effective_bb: float
    pot_bb: float


def synthetic_situation(*, bb_min: float = 5.0, bb_max: float = 40.0,
                         pot_bb: float = 1.5, seed: int | None = None) -> TrainingSituation:
    """Sorteia um spot de push/fold sintético (classe de mão uniforme
    entre as 169, stack uniforme no intervalo) — resolvido ao vivo pelo
    Nash, não uma tabela pré-definida."""
    rng = random.Random(seed)
    ranking = pf_equity.build_ranking()
    hand_class = rng.choice(ranking)
    combo = pf_equity.class_representative(hand_class)
    return TrainingSituation(
        source="synthetic", site=None, hand_id=None, position=None,
        hero_cards=hand_str(combo), hand_class=hand_class,
        effective_bb=round(rng.uniform(bb_min, bb_max), 1), pot_bb=pot_bb,
    )


def historical_situation(df, *, seed: int | None = None) -> TrainingSituation | None:
    """Sorteia uma decisão REAL de abertura preflop já exportada (Fase 1,
    `rl/export.py`) — esconde a ação que o hero de fato tomou no passado
    (é isso que o usuário vai decidir agora, não repetir o que já fez).
    `None` se o dataset não tiver nenhum spot `preflop_open` utilizável."""
    sub = df[df["context_type"] == "preflop_open"].dropna(
        subset=["effective_stack_bb", "pot_before_action_bb", "hero_cards"])
    if sub.empty:
        return None
    row = sub.sample(1, random_state=seed).iloc[0]
    hand_class = pf_equity.class_of(parse_hand(row["hero_cards"]))
    return TrainingSituation(
        source="historical", site=row["site"], hand_id=row["hand_id"],
        position=row["position"], hero_cards=row["hero_cards"], hand_class=hand_class,
        effective_bb=float(row["effective_stack_bb"]), pot_bb=float(row["pot_before_action_bb"]),
    )


@dataclass
class TrainingFeedback:
    situation: TrainingSituation
    user_action: str
    personal_policy_action: str | None
    personal_policy_probs: dict[str, float] | None
    reference_action: str
    ev_user_bb: float
    ev_reference_bb: float
    ev_gap_bb: float


def evaluate_response(situation: TrainingSituation, user_action: str,
                       *, personal_policy=None) -> TrainingFeedback:
    """Avalia a resposta do usuário pro `situation` — Nash é a referência
    de verdade (mesmo motor de `context.py`/`pushfold_env.py`); Personal
    Policy é só informativa (o que o hero HISTORICAMENTE faria), não
    substitui a referência."""
    if user_action not in ("push", "fold"):
        raise ValueError(f"user_action precisa ser 'push' ou 'fold', recebeu {user_action!r}")

    eb, pb = _round_for_cache(situation.effective_bb, situation.pot_bb)
    result = pf_analyze._cached_solve(eb, pb)
    grid, _ = pf_nash.ev_grid(situation.effective_bb, situation.pot_bb, result=result)

    ev_push = float(grid[situation.hand_class])
    # Referência = sinal do EV, não "está na shove_classes do equilíbrio
    # de fictitious play" — as duas podem discordar em spots de fronteira
    # (mesmo fenômeno documentado em context.py e em pushfold_env.py) e
    # usar a range de equilíbrio aqui podia gerar um ev_gap NEGATIVO
    # (referência pior que a ação do usuário), o que não faz sentido pra
    # essa finalidade.
    reference_action = "push" if ev_push > 0 else "fold"
    ev_reference = ev_push if reference_action == "push" else 0.0
    ev_user = ev_push if user_action == "push" else 0.0

    personal_policy_action = None
    personal_policy_probs = None
    if personal_policy is not None:
        state = dict(
            street="preflop", position=situation.position or "BTN",
            hero_cards=situation.hero_cards, context_type="preflop_open",
            effective_stack_bb=situation.effective_bb, pot_before_action_bb=situation.pot_bb,
        )
        personal_policy_probs = personal_policy.predict_proba(state)
        personal_policy_action = personal_policy.recommend(state)

    return TrainingFeedback(
        situation=situation, user_action=user_action,
        personal_policy_action=personal_policy_action, personal_policy_probs=personal_policy_probs,
        reference_action=reference_action, ev_user_bb=round(ev_user, 3),
        ev_reference_bb=round(ev_reference, 3), ev_gap_bb=round(ev_reference - ev_user, 3),
    )


def log_feedback(conn, feedback: TrainingFeedback) -> None:
    s = feedback.situation
    dbm.log_adaptive_trainer_answer(
        conn, source=s.source, site=s.site, hand_id=s.hand_id, position=s.position,
        hero_cards=s.hero_cards, effective_bb=s.effective_bb, pot_bb=s.pot_bb,
        user_action=feedback.user_action, personal_policy_action=feedback.personal_policy_action,
        reference_action=feedback.reference_action, ev_user_bb=feedback.ev_user_bb,
        ev_reference_bb=feedback.ev_reference_bb, ev_gap_bb=feedback.ev_gap_bb,
    )


def format_situation(s: TrainingSituation) -> str:
    pos = f" | posição {s.position}" if s.position else ""
    return f"[{s.source}] {s.hero_cards} ({s.hand_class}){pos} | stack efetivo {s.effective_bb}BB | pote {s.pot_bb}BB"


def format_feedback(f: TrainingFeedback) -> str:
    lines = [
        f"Sua ação:            {f.user_action}",
        f"Referência (Nash):   {f.reference_action}",
    ]
    if f.personal_policy_action is not None:
        probs = ", ".join(f"{k}={v:.2f}" for k, v in sorted(f.personal_policy_probs.items(), key=lambda kv: -kv[1]))
        lines.append(f"Personal Policy:     {f.personal_policy_action}  ({probs})")
    lines += [
        f"EV(sua ação):        {f.ev_user_bb:+.3f} BB",
        f"EV(referência):      {f.ev_reference_bb:+.3f} BB",
        f"EV gap:              {f.ev_gap_bb:+.3f} BB"
        + ("  <- alinhado com Nash" if f.ev_gap_bb == 0 else ""),
    ]
    return "\n".join(lines)
