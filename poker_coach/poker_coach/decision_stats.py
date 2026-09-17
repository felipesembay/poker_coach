"""Estatísticas sobre `decision_analysis` (Etapa 7 do Poker Decision
Engine, seção 11.2 do plano) — 3 categorias, cada uma segmentada por
`model_type` e nunca misturadas entre si (seção 11.3: EV Nash isolado,
EV contextual e resultado realizado são coisas diferentes).

Todas as médias ignoram linhas com valor NULL no campo em questão (não
força um 0 onde não há dado — evita "não temos essa mão nesse contexto"
virar silenciosamente "essa mão vale 0").
"""
from __future__ import annotations

STACK_BUCKETS = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 50)]


def _avg(vals: list[float | None]) -> float | None:
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _round(v: float | None, nd: int = 3) -> float | None:
    return round(v, nd) if v is not None else None


def _round_pct(v: float | None) -> float | None:
    return round(v * 100, 1) if v is not None else None


def preflop_model_performance(conn) -> dict:
    """Decisões avaliadas pelo Nash push/fold isolado (model_type=
    'pushfold_nash'): EV teórico, resultado realizado (da MÃO INTEIRA —
    ver docstring de `replay_decision.build_decision_analysis_record`,
    não é o EV incremental dessa decisão), e frequência de decisão fora
    do que o modelo recomendaria."""
    rows = conn.execute(
        """SELECT ev_push_bb, actual_result_bb, recommended_action, actual_action
           FROM decision_analysis WHERE model_type='pushfold_nash'"""
    ).fetchall()
    n = len(rows)
    if n == 0:
        return {
            "n": 0, "avg_ev_theoretical_bb": None, "avg_actual_result_bb": None,
            "error_rate_pct": None, "avg_ev_lost_on_error_bb": None,
        }

    def _acted_push(action: str | None) -> bool | None:
        if action is None:
            return None
        return action in ("push", "raise", "allin", "bet")

    errors = 0
    comparable = 0
    ev_lost: list[float] = []
    for ev, _result, rec, act in rows:
        acted_push = _acted_push(act)
        if rec is None or acted_push is None:
            continue
        comparable += 1
        if (rec == "push") != acted_push:
            errors += 1
            if ev is not None:
                ev_lost.append(abs(ev))

    return {
        "n": n,
        "avg_ev_theoretical_bb": _round(_avg([r[0] for r in rows])),
        "avg_actual_result_bb": _round(_avg([r[1] for r in rows])),
        "error_rate_pct": round(errors / comparable * 100, 1) if comparable else None,
        "avg_ev_lost_on_error_bb": _round(_avg(ev_lost)) if ev_lost else (0.0 if comparable else None),
    }


def contextual_decision_performance(conn) -> dict:
    """Decisões com ação anterior (model_type='contextual_ev'): equity
    estimada, required equity, EV de cada ação aplicável, e frequência
    de decisão diferente da recomendação de maior EV."""
    rows = conn.execute(
        """SELECT hero_equity, required_equity, ev_call_bb, ev_fold_bb, ev_push_bb,
                  recommended_action, actual_action, actual_result_bb
           FROM decision_analysis WHERE model_type='contextual_ev'"""
    ).fetchall()
    n = len(rows)
    if n == 0:
        return {
            "n": 0, "avg_hero_equity_pct": None, "avg_required_equity_pct": None,
            "avg_ev_call_bb": None, "avg_ev_fold_bb": None, "avg_ev_push_bb": None,
            "error_rate_pct": None, "avg_actual_result_bb": None,
        }

    errors = 0
    comparable = 0
    for _eq, _req, _c, _f, _p, rec, act, _res in rows:
        if rec is None or act is None:
            continue
        comparable += 1
        if rec != act:
            errors += 1

    return {
        "n": n,
        "avg_hero_equity_pct": _round_pct(_avg([r[0] for r in rows])),
        "avg_required_equity_pct": _round_pct(_avg([r[1] for r in rows])),
        "avg_ev_call_bb": _round(_avg([r[2] for r in rows])),
        "avg_ev_fold_bb": _round(_avg([r[3] for r in rows])),
        "avg_ev_push_bb": _round(_avg([r[4] for r in rows])),
        "error_rate_pct": round(errors / comparable * 100, 1) if comparable else None,
        "avg_actual_result_bb": _round(_avg([r[7] for r in rows])),
    }


def _flop_texture(board: str | None) -> str | None:
    """Textura do FLOP (3 primeiras cartas do board salvo) — pareado ou
    não, e quantas cartas do mesmo naipe (monotone/two-tone/rainbow).
    Não classifica turn/river à parte (o board salvo em cada linha já é
    o board como estava NAQUELE passo — texturas de turn/river ficam
    fora de escopo nesta etapa, documentado, não fabricado)."""
    if not board:
        return None
    cards = board.split()
    if len(cards) < 3:
        return None
    ranks = [c[0] for c in cards[:3]]
    suits = [c[1] for c in cards[:3]]
    paired = len(set(ranks)) < 3
    max_suited = max(suits.count(s) for s in set(suits))
    flush_texture = {3: "monotone", 2: "two-tone"}.get(max_suited, "rainbow")
    return f"{'paired' if paired else 'unpaired'}-{flush_texture}"


def postflop_performance(conn) -> dict:
    """Decisões pós-flop (flop/turn/river, qualquer model_type — inclui
    'contextual_ev' e 'postflop_check_only'), quebradas por street,
    posição, faixa de stack efetivo e textura do flop."""
    base_where = "street IN ('flop','turn','river')"

    by_street = []
    for street in ("flop", "turn", "river"):
        rows = conn.execute(
            f"""SELECT hero_equity, ev_call_bb, required_equity, actual_result_bb
                FROM decision_analysis WHERE {base_where} AND street=?""",
            (street,),
        ).fetchall()
        by_street.append({
            "street": street, "n": len(rows),
            "avg_hero_equity_pct": _round_pct(_avg([r[0] for r in rows])),
            "avg_ev_call_bb": _round(_avg([r[1] for r in rows])),
            "avg_required_equity_pct": _round_pct(_avg([r[2] for r in rows])),
            "avg_actual_result_bb": _round(_avg([r[3] for r in rows])),
        })

    positions = [
        r[0] for r in conn.execute(
            f"SELECT DISTINCT position FROM decision_analysis WHERE {base_where} "
            "AND position IS NOT NULL"
        ).fetchall()
    ]
    by_position = []
    for pos in sorted(positions):
        rows = conn.execute(
            f"""SELECT hero_equity, actual_result_bb FROM decision_analysis
                WHERE {base_where} AND position=?""",
            (pos,),
        ).fetchall()
        by_position.append({
            "position": pos, "n": len(rows),
            "avg_hero_equity_pct": _round_pct(_avg([r[0] for r in rows])),
            "avg_actual_result_bb": _round(_avg([r[1] for r in rows])),
        })

    by_stack = []
    for lo, hi in STACK_BUCKETS:
        rows = conn.execute(
            f"""SELECT hero_equity, actual_result_bb FROM decision_analysis
                WHERE {base_where} AND effective_stack_bb >= ? AND effective_stack_bb < ?""",
            (lo, hi),
        ).fetchall()
        by_stack.append({
            "bucket": f"{lo:g}-{hi:g}BB", "n": len(rows),
            "avg_hero_equity_pct": _round_pct(_avg([r[0] for r in rows])),
            "avg_actual_result_bb": _round(_avg([r[1] for r in rows])),
        })

    texture_rows = conn.execute(
        f"SELECT board, hero_equity, actual_result_bb FROM decision_analysis "
        f"WHERE {base_where} AND board IS NOT NULL"
    ).fetchall()
    texture_groups: dict[str, list[tuple[float | None, float | None]]] = {}
    for board, eq, result in texture_rows:
        texture = _flop_texture(board)
        if texture is None:
            continue
        texture_groups.setdefault(texture, []).append((eq, result))
    by_texture = [
        {
            "texture": texture, "n": len(vals),
            "avg_hero_equity_pct": _round_pct(_avg([v[0] for v in vals])),
            "avg_actual_result_bb": _round(_avg([v[1] for v in vals])),
        }
        for texture, vals in sorted(texture_groups.items())
    ]

    return {
        "by_street": by_street,
        "by_position": by_position,
        "by_stack": by_stack,
        "by_texture": by_texture,
    }
