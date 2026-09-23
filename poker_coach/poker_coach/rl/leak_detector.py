"""Fase 3 do plano de RL — Leak Detector.

NÃO é RL, e não deve ser chamado de RL — é um detector de padrão
OFFLINE/SUPERVISIONADO sobre o dataset de decisão (`rl/export.py`).
Diferença central pro Behavioral Cloning (Fase 2, que modela "o que o
hero faria") e pro EV/Nash existente (que já dá a referência por
decisão): aqui a pergunta é "onde o COMPORTAMENTO do hero diverge da
referência de forma consistente o bastante pra valer a pena confiar".

Princípios que o usuário pediu explicitamente e que este módulo respeita:

1. NUNCA usa `actual_result_bb` como alvo — só `ev_gap` (vem do motor
   EV/Nash existente, não do resultado da mão). Ver separação OUTCOME vs
   DECISION QUALITY em `export.py`.
2. NUNCA vira "leak" só porque `ev_gap > 0` numa decisão ISOLADA — o que
   entra no relatório é sempre uma AGREGAÇÃO por categoria de
   comportamento, com `sample_size`, `mean/median/std_ev_gap` e
   `reference_coverage` (não confunde "essa decisão teve ev_gap alto" com
   "esse padrão é um leak confiável").
3. NUNCA cria ranking absoluto de "piores leaks" sem mostrar o tamanho da
   amostra ao lado — `format_leak_report` sempre imprime `n=` e
   `confidence=` junto de qualquer EV.
4. Categoria "sizing" (pré-flop e pós-flop) EXISTE na taxonomia pedida
   mas é reportada como NÃO MENSURÁVEL nesta fase: o motor atual
   (`ev_engine.py`) não modela o tamanho de aposta/raise do hero, só
   fold/call/push/check (ver docstring de `ev_engine.py`, `_ENGINE_ACTIONS`
   em `export.py`). Não inventamos uma métrica de qualidade de sizing só
   pra preencher a categoria.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Reaproveita a mesma convenção de faixa de stack de `decision_stats.py`
# (STACK_BUCKETS), estendida com uma faixa aberta pra stacks fundos (o
# dataset real de MTT tem mãos com 80-100+ BB, fora do alcance original
# de decision_stats que foca em short stack).
STACK_BUCKETS: list[tuple[float, float | None]] = [
    (0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 50), (50, None),
]

# Limiares de confiança — heurística simples e declarada, não um teste
# estatístico formal (seção 11 do plano: evitar conclusão com amostra
# pequena, não fingir rigor que não existe).
_CONFIDENCE_LOW, _CONFIDENCE_HIGH = 20, 100
_CONFIDENCE_ORDER = {"baixa": 0, "média": 1, "alta": 2}

SIZING_NOTE = (
    "Categoria \"sizing\" (pré-flop e pós-flop) não é mensurável nesta fase: "
    "o motor de EV atual (ev_engine.py) não modela o tamanho de aposta/raise "
    "do hero, só fold/call/push/check. Fica para quando o motor ganhar um "
    "modelo de bet-sizing — não inventamos uma métrica aqui."
)


def stack_bucket_label(effective_stack_bb: float | None) -> str | None:
    if effective_stack_bb is None or pd.isna(effective_stack_bb):
        return None
    for lo, hi in STACK_BUCKETS:
        if hi is None:
            if effective_stack_bb >= lo:
                return f"{lo}+"
        elif lo <= effective_stack_bb < hi:
            return f"{lo}-{hi}"
    return None


def _confidence(n: int) -> str:
    if n < _CONFIDENCE_LOW:
        return "baixa"
    if n < _CONFIDENCE_HIGH:
        return "média"
    return "alta"


def classify_leak_direction(actual_action_class: str | None, reference_action: str | None) -> str | None:
    """Direção da divergência comportamental vs a referência (Nash ou EV
    engine, já calculada em `export.py`) — `None` quando alinhado ou sem
    referência disponível (não é leak, não entra em nenhuma agregação).

    Vocabulário de ação da referência é sempre um de {fold, call, check,
    push} (ver `export.resolve_actual_engine_action` — o motor não avalia
    bet/raise não-all-in), então a direção é derivada só a partir disso,
    nunca inventada."""
    if not reference_action or not actual_action_class or actual_action_class == reference_action:
        return None
    if actual_action_class == "fold":
        return "over-fold"
    if reference_action == "fold":
        if actual_action_class == "call":
            return "over-call"
        if actual_action_class in ("bet", "raise", "push"):
            return "over-bluff"
        return "diverge-outro"
    if reference_action in ("push", "call", "bet", "raise") and actual_action_class in ("check", "call"):
        return "under-bluff"
    return "diverge-outro"


def leak_category(street: str, context_type: str | None, actual_action_class: str | None,
                   reference_action: str | None) -> str | None:
    """Nome de categoria no vocabulário pedido (push/fold, under-3bet,
    over-fold, over-call, over-bluff, under-bluff, river) — mapeado a
    partir da direção honesta acima, nunca inventado a partir de uma
    decisão isolada. "under-3bet" é o nome idiomático de "under-bluff"
    especificamente quando o hero está respondendo a uma aposta/raise
    PREFLOP (a ação de referência mais agressiva ali É re-raise all-in)."""
    direction = classify_leak_direction(actual_action_class, reference_action)
    if direction is None:
        return None
    is_push_fold_spot = context_type == "preflop_open"
    if street == "preflop":
        if is_push_fold_spot:
            return f"preflop.push_fold.{direction}"
        if direction == "under-bluff":
            return "preflop.facing.under-3bet"
        return f"preflop.facing.{direction}"
    if street == "river":
        return f"river.{direction}"
    return f"postflop.{direction}"  # flop/turn


def add_leak_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["leak_direction"] = [
        classify_leak_direction(a, r)
        for a, r in zip(df["action_class"], df["reference_action"])
    ]
    df["leak_category"] = [
        leak_category(s, c, a, r)
        for s, c, a, r in zip(df["street"], df["context_type"], df["action_class"], df["reference_action"])
    ]
    df["stack_bucket"] = df["effective_stack_bb"].map(stack_bucket_label)
    return df


def aggregate_leaks(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Agrega SÓ decisões com `leak_category` != None (divergência real da
    referência), por `group_cols` — nunca por decisão isolada. Cada linha
    do resultado tem `sample_size`/`reference_coverage`/`confidence` ao
    lado de qualquer estatística de `ev_gap`."""
    if "leak_category" not in df.columns:
        df = add_leak_columns(df)
    leaks = df[df["leak_category"].notna()]
    if leaks.empty:
        return pd.DataFrame(columns=[*group_cols, "sample_size", "reference_coverage",
                                      "mean_ev_gap", "median_ev_gap", "std_ev_gap", "confidence"])

    rows = []
    for keys, g in leaks.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        ev = g["ev_gap"].dropna()
        n = len(g)
        rows.append({
            **dict(zip(group_cols, keys)),
            "sample_size": n,
            "reference_coverage": round(len(ev) / n, 3) if n else None,
            "mean_ev_gap": round(float(ev.mean()), 3) if len(ev) else None,
            "median_ev_gap": round(float(ev.median()), 3) if len(ev) else None,
            "std_ev_gap": round(float(ev.std()), 3) if len(ev) > 1 else (0.0 if len(ev) == 1 else None),
            "confidence": _confidence(n),
        })
    return pd.DataFrame(rows).sort_values("sample_size", ascending=False).reset_index(drop=True)


@dataclass
class LeakReport:
    by_category: pd.DataFrame
    by_category_position: pd.DataFrame
    by_category_stack: pd.DataFrame
    by_category_context: pd.DataFrame
    n_decisions: int
    n_leaks: int
    n_reference_available: int


def build_leak_report(df: pd.DataFrame) -> LeakReport:
    df = add_leak_columns(df)
    return LeakReport(
        by_category=aggregate_leaks(df, ["leak_category"]),
        by_category_position=aggregate_leaks(df, ["leak_category", "position"]),
        by_category_stack=aggregate_leaks(df, ["leak_category", "stack_bucket"]),
        by_category_context=aggregate_leaks(df, ["leak_category", "context_type"]),
        n_decisions=len(df),
        n_leaks=int(df["leak_category"].notna().sum()),
        n_reference_available=int(df["reference_action"].notna().sum()),
    )


def format_leak_report(report: LeakReport, *, min_confidence: str = "média", top_n: int = 10) -> str:
    lines = [
        "=== Leak Detector — Fase 3 ===", "",
        f"Decisões no dataset: {report.n_decisions} | com referência: {report.n_reference_available} | "
        f"divergentes da referência (leak_category != None): {report.n_leaks}",
        "",
        SIZING_NOTE, "",
        "Por categoria (TODAS, ordenado por amostra — não por EV, pra não sugerir "
        "que amostra pequena é confiável):",
    ]
    for _, r in report.by_category.iterrows():
        ev_part = (
            f"mean_ev_gap={r['mean_ev_gap']:+.3f} median={r['median_ev_gap']:+.3f} std={r['std_ev_gap']:.3f}"
            if pd.notna(r["mean_ev_gap"]) else "(sem ev_gap disponível nessa categoria)"
        )
        lines.append(
            f"  {r['leak_category']:<32} n={r['sample_size']:>4}  conf={r['confidence']:<6}  "
            f"cobertura_ref={r['reference_coverage']}  {ev_part}"
        )

    lines.append("")
    lines.append(
        f"Top {top_n} por EV médio perdido — SÓ confiança >= '{min_confidence}' "
        "(N e confiança sempre exibidos, nunca um ranking cego):"
    )
    order = _CONFIDENCE_ORDER
    ranked = report.by_category[report.by_category["confidence"].map(order) >= order[min_confidence]]
    ranked = ranked.dropna(subset=["mean_ev_gap"]).sort_values("mean_ev_gap", ascending=False)
    if ranked.empty:
        lines.append(f"  (nenhuma categoria com confiança >= '{min_confidence}' e ev_gap disponível)")
    for _, r in ranked.head(top_n).iterrows():
        lines.append(
            f"  {r['leak_category']:<32} mean_ev_gap={r['mean_ev_gap']:+.3f}  "
            f"n={r['sample_size']}  conf={r['confidence']}"
        )

    lines.append("")
    lines.append("Onde as 3 categorias mais amostradas mais aparecem (posição / faixa de stack):")
    top_categories = report.by_category.head(3)["leak_category"].tolist()
    for cat in top_categories:
        lines.append(f"\n  [{cat}]")
        by_pos = report.by_category_position[report.by_category_position["leak_category"] == cat]
        by_pos = by_pos.sort_values("sample_size", ascending=False).head(5)
        lines.append("    por posição: " + ", ".join(
            f"{row['position']}(n={row['sample_size']})" for _, row in by_pos.iterrows()
        ))
        by_stack = report.by_category_stack[report.by_category_stack["leak_category"] == cat]
        by_stack = by_stack.sort_values("sample_size", ascending=False).head(5)
        lines.append("    por stack: " + ", ".join(
            f"{row['stack_bucket']}(n={row['sample_size']})" for _, row in by_stack.iterrows()
        ))

    return "\n".join(lines)
