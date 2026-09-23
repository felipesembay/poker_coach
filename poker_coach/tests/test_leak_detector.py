"""Testes de poker_coach/rl/leak_detector.py (Fase 3).

Cobre exatamente as regras que o usuário pediu explicitamente: nunca
marcar leak por decisão isolada sem agregação, nunca ranquear sem mostrar
amostra, nunca usar actual_result_bb, categoria "sizing" reportada como
não mensurável (não inventada)."""
import pathlib
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.rl import leak_detector as ld


def test_stack_bucket_label_covers_open_ended_range():
    assert ld.stack_bucket_label(3) == "0-5"
    assert ld.stack_bucket_label(17) == "15-20"
    assert ld.stack_bucket_label(84.5) == "50+"
    assert ld.stack_bucket_label(None) is None


@pytest.mark.parametrize("actual,reference,expected", [
    ("fold", "push", "over-fold"),
    ("fold", "call", "over-fold"),
    ("call", "fold", "over-call"),
    ("push", "fold", "over-bluff"),
    ("bet", "fold", "over-bluff"),
    ("check", "push", "under-bluff"),
    ("call", "push", "under-bluff"),
    ("push", "push", None),  # alinhado — não é leak
    ("fold", None, None),  # sem referência — não é leak
])
def test_classify_leak_direction(actual, reference, expected):
    assert ld.classify_leak_direction(actual, reference) == expected


def test_leak_category_preflop_open_uses_push_fold_label():
    cat = ld.leak_category("preflop", "preflop_open", "fold", "push")
    assert cat == "preflop.push_fold.over-fold"


def test_leak_category_preflop_facing_raise_under_bluff_becomes_under_3bet():
    cat = ld.leak_category("preflop", "preflop_facing_raise", "call", "push")
    assert cat == "preflop.facing.under-3bet"


def test_leak_category_river_gets_its_own_bucket_not_postflop():
    cat = ld.leak_category("river", "river_facing_bet", "fold", "call")
    assert cat == "river.over-fold"


def test_leak_category_flop_turn_are_generic_postflop():
    assert ld.leak_category("flop", "flop_facing_bet", "fold", "call") == "postflop.over-fold"
    assert ld.leak_category("turn", "turn_facing_bet", "fold", "call") == "postflop.over-fold"


def _synthetic_df():
    rows = []
    # 25 decisões over-fold no push/fold preflop, com ev_gap variado —
    # amostra >= 20 -> confiança "média".
    for i in range(25):
        rows.append({
            "street": "preflop", "context_type": "preflop_open", "position": "BTN",
            "action_class": "fold", "reference_action": "push",
            "ev_gap": 1.0 + (i % 5) * 0.1, "effective_stack_bb": 15 + i % 3,
        })
    # 5 decisões alinhadas (não são leak, não devem aparecer na agregação).
    for i in range(5):
        rows.append({
            "street": "preflop", "context_type": "preflop_open", "position": "BTN",
            "action_class": "push", "reference_action": "push",
            "ev_gap": 0.0, "effective_stack_bb": 15,
        })
    # 3 decisões over-fold com ev_gap indisponível (ação não modelada) —
    # devem contar pro sample_size mas não pra média de ev_gap.
    for i in range(3):
        rows.append({
            "street": "flop", "context_type": "flop_facing_bet", "position": "BB",
            "action_class": "fold", "reference_action": "call",
            "ev_gap": None, "effective_stack_bb": 40,
        })
    return pd.DataFrame(rows)


def test_add_leak_columns_only_flags_real_divergence():
    df = ld.add_leak_columns(_synthetic_df())
    aligned = df[df["action_class"] == df["reference_action"]]
    assert aligned["leak_category"].isna().all()
    diverged = df[df["action_class"] != df["reference_action"]]
    assert diverged["leak_category"].notna().all()


def test_aggregate_leaks_never_uses_actual_result_bb_and_has_confidence():
    df = ld.add_leak_columns(_synthetic_df())
    assert "actual_result_bb" not in df.columns  # dataset sintético nem tem — prova que não é exigido
    agg = ld.aggregate_leaks(df, ["leak_category"])
    row = agg[agg["leak_category"] == "preflop.push_fold.over-fold"].iloc[0]
    assert row["sample_size"] == 25
    assert row["confidence"] == "média"  # 20 <= n < 100
    assert row["mean_ev_gap"] is not None
    assert row["reference_coverage"] == 1.0  # todas as 25 tinham ev_gap


def test_aggregate_leaks_reference_coverage_partial_when_some_ev_gap_missing():
    df = ld.add_leak_columns(_synthetic_df())
    agg = ld.aggregate_leaks(df, ["leak_category"])
    row = agg[agg["leak_category"] == "postflop.over-fold"].iloc[0]
    assert row["sample_size"] == 3
    assert row["confidence"] == "baixa"  # n < 20
    assert pd.isna(row["mean_ev_gap"])  # todos os ev_gap eram None (NaN na coluna float do pandas)
    assert row["reference_coverage"] == 0.0


def test_format_leak_report_handles_nan_ev_gap_without_printing_nan():
    """Regressão: pandas guarda `mean_ev_gap=None` numa coluna float como
    NaN, não None — um check `is not None` deixa passar e formata "nan"
    em vez de mostrar a mensagem de "sem ev_gap disponível"."""
    report = ld.build_leak_report(_synthetic_df())
    text = ld.format_leak_report(report)
    assert "sem ev_gap disponível nessa categoria" in text
    assert "mean_ev_gap=nan" not in text


def test_build_leak_report_and_format_includes_sizing_disclaimer():
    report = ld.build_leak_report(_synthetic_df())
    assert report.n_leaks == 28  # 25 + 3 (as 5 alinhadas não contam)
    text = ld.format_leak_report(report)
    assert "sizing" in text.lower()
    assert "não é mensurável" in text
    # toda linha de ranking mostra n= e conf= — nunca ranking cego.
    assert "n=" in text and "conf=" in text


def test_format_leak_report_high_confidence_filter_excludes_low_n():
    report = ld.build_leak_report(_synthetic_df())
    text = ld.format_leak_report(report, min_confidence="alta")
    # nenhuma categoria sintética chega a n>=100 (confiança "alta") —
    # o ranking filtrado deve dizer explicitamente que não achou nada,
    # não inventar um ranking com amostra insuficiente.
    assert "nenhuma categoria com confiança" in text
