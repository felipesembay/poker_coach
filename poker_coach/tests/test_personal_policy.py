"""Testes de poker_coach/rl/personal_policy.py (Fase 2 — Behavioral
Cloning). Usa um dataset sintético pequeno (não o parquet real de
produção) — só precisa validar a mecânica: split temporal reusado,
pipeline treina/prevê, métricas fazem sentido, load/predict_proba/
recommend funcionam num artefato salvo em disco."""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.rl import personal_policy as pp

pytest.importorskip("sklearn")


def _synthetic_dataset(n=300, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        equity = rng.uniform(0, 1)
        # comportamento sintético mas aprendível: equity alta -> push/call,
        # equity baixa -> fold, pra garantir que o classificador aprenda
        # algo acima de "chute a classe majoritária".
        if equity > 0.6:
            action = rng.choice(["push", "call", "raise"])
        elif equity > 0.35:
            action = rng.choice(["call", "check"])
        else:
            action = rng.choice(["fold", "fold", "check"])
        rows.append({
            "site": "test", "hand_id": f"h{i}", "step_order": 1,
            "ts": f"2026-01-{(i % 27) + 1:02d}T00:00:00",
            "street": "preflop", "position": "BTN",
            "hero_cards": "As Kd", "context_type": "preflop_open",
            "effective_stack_bb": rng.uniform(5, 100),
            "pot_before_action_bb": rng.uniform(1, 5),
            "bet_faced_bb": None, "call_cost_bb": None,
            "number_of_opponents": None,
            "hero_equity": equity, "required_equity": None,
            "action_class": action,
        })
    return pd.DataFrame(rows)


def test_add_hero_hand_class_reuses_nash_classifier():
    df = pd.DataFrame({"hero_cards": ["As Kd", "Qs Qh", None, ""]})
    out = pp.add_hero_hand_class(df)
    assert out["hero_hand_class"].iloc[0] == "AKo"
    assert out["hero_hand_class"].iloc[1] == "QQ"
    assert pd.isna(out["hero_hand_class"].iloc[2])
    assert pd.isna(out["hero_hand_class"].iloc[3])


def test_prepare_dataset_filters_unknown_action_and_adds_hand_class():
    df = pd.DataFrame({
        "hero_cards": ["As Kd", "Qs Qh"],
        "action_class": ["fold", "show"],  # "show" não é uma ação de behavior válida
    })
    out = pp.prepare_dataset(df)
    assert len(out) == 1
    assert out.iloc[0]["hero_hand_class"] == "AKo"


def test_train_and_evaluate_beats_majority_baseline():
    df = _synthetic_dataset(n=400)
    report, pipeline = pp.train_and_evaluate(df)

    assert report.train_n + report.val_n + report.test_n == len(pp.prepare_dataset(df))
    assert report.chosen_model in pp._model_factories()
    t = report.test_result
    # nao e so decorar "fold" (a classe mais comum no dataset sintetico) —
    # tem que aproveitar o sinal de hero_equity, que e claramente informativo.
    assert t.balanced_accuracy > 0.35
    assert set(t.labels) <= set(pp.ACTION_CLASSES)
    assert t.confusion.shape == (len(t.labels), len(t.labels))
    # calibração: soma das frequências empíricas tem que fechar em 1.
    assert t.calibration["empirical_freq"].sum() == pytest.approx(1.0)


def test_save_and_load_policy_roundtrip(tmp_path):
    df = _synthetic_dataset(n=300)
    _report, pipeline = pp.train_and_evaluate(df)
    path = tmp_path / "policy.pkl"
    pp.save_policy(pipeline, str(path))

    loaded = pp.load_policy(str(path))
    state = {
        "street": "preflop", "position": "BTN", "hero_cards": "As Kd",
        "context_type": "preflop_open", "effective_stack_bb": 40.0,
        "pot_before_action_bb": 1.5, "hero_equity": 0.8,
    }
    probs = loaded.predict_proba(state)
    assert set(probs) == set(pipeline.classes_)
    assert pytest.approx(sum(probs.values()), abs=1e-6) == 1.0
    assert loaded.recommend(state) == max(probs, key=probs.get)


def test_multiclass_brier_is_zero_for_perfect_prediction():
    proba = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    y_idx = np.array([0, 1])
    assert pp._multiclass_brier(y_idx, proba, 3) == pytest.approx(0.0)
