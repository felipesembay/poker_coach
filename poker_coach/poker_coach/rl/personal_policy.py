"""Fase 2 do plano de RL — Behavioral Cloning / Personal Policy.

Objetivo (seção 7 do plano do usuário): aprender `state -> P(action)`, ou
seja, modelar o COMPORTAMENTO histórico do hero — "dado esse estado, qual
ação ele provavelmente tomaria" — não jogar poker melhor. Isso é
explicitamente diferente do Leak Detector (Fase 3, supervisionado sobre
EV_gap) e do RL de push/fold (Fase 4/5, ambiente + reward): aqui o alvo é
a ação observada, ponto.

Reaproveita:
- `rl.export.temporal_split` pro split treino/validação/teste (não reimplementa).
- `handeval.parse_hand` + `pushfold.equity.class_of` pra derivar a classe
  de 169 mãos (ex. "AKs") a partir de `hero_cards` — mesma convenção usada
  no motor Nash existente, não uma codificação nova.

Modelos testados nesta ordem (do mais simples ao mais complexo, como
pedido — não começa com deep learning): Logistic Regression, Random
Forest, Gradient Boosting (todos scikit-learn). O melhor por
`balanced_accuracy` na validação é o escolhido; teste final só é olhado
uma vez, no modelo já escolhido — não usado pra escolher entre modelos
(evita otimismo por vazamento de seleção)."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from ..handeval import parse_hand
from ..pushfold.equity import class_of
from .export import temporal_split

ACTION_CLASSES = ["fold", "check", "call", "bet", "raise", "push"]

NUMERIC_FEATURES = [
    "effective_stack_bb", "pot_before_action_bb", "bet_faced_bb", "call_cost_bb",
    "number_of_opponents", "hero_equity", "required_equity",
]
CATEGORICAL_FEATURES = ["street", "position", "context_type", "hero_hand_class"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def add_hero_hand_class(df: pd.DataFrame) -> pd.DataFrame:
    """Deriva `hero_hand_class` (ex. "AKs", "QQ") de `hero_cards` — reusa
    o mesmo parser/classificador do motor Nash (`pushfold/equity.py`),
    não inventa uma codificação de mão nova só pra isso."""
    df = df.copy()

    def _cls(cards):
        if not isinstance(cards, str) or not cards.strip():
            return None
        try:
            return class_of(parse_hand(cards))
        except (KeyError, IndexError, ValueError):
            return None

    df["hero_hand_class"] = df["hero_cards"].map(_cls)
    return df


def prepare_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra pras linhas com ação num vocabulário conhecido e adiciona
    `hero_hand_class`. Não filtra por `reference_source` — Behavioral
    Cloning aprende do COMPORTAMENTO observado, que existe mesmo quando a
    referência de EV não deu (ver `rl/export.py`)."""
    df = add_hero_hand_class(df)
    return df[df["action_class"].isin(ACTION_CLASSES)].copy()


def _build_pipeline(model):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="constant", fill_value="__missing__")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])
    pre = ColumnTransformer([
        ("num", numeric, NUMERIC_FEATURES),
        ("cat", categorical, CATEGORICAL_FEATURES),
    ])
    return Pipeline([("pre", pre), ("clf", model)])


def _model_factories() -> dict:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    return {
        "logistic_regression": lambda: LogisticRegression(
            max_iter=2000, class_weight="balanced",
        ),
        "random_forest": lambda: RandomForestClassifier(
            n_estimators=300, min_samples_leaf=5, class_weight="balanced",
            random_state=0, n_jobs=-1,
        ),
        "gradient_boosting": lambda: GradientBoostingClassifier(
            n_estimators=150, max_depth=3, random_state=0,
        ),
    }


def _multiclass_brier(y_true_idx: np.ndarray, proba: np.ndarray, n_classes: int) -> float:
    """Generalização multiclasse do Brier score (MSE entre a distribuição
    prevista e o one-hot da classe real) — sklearn só tem versão binária
    (`brier_score_loss`)."""
    onehot = np.eye(n_classes)[y_true_idx]
    return float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))


@dataclass
class EvalResult:
    n: int
    accuracy: float
    balanced_accuracy: float
    macro_f1: float
    log_loss: float
    brier: float
    confusion: np.ndarray
    labels: list[str]
    calibration: pd.DataFrame  # por classe: prob. média prevista vs. frequência empírica


def evaluate(pipeline, X: pd.DataFrame, y: pd.Series) -> EvalResult:
    from sklearn.metrics import (
        accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score, log_loss,
    )

    proba = pipeline.predict_proba(X)
    classes = list(pipeline.classes_)
    pred = pipeline.predict(X)
    y_arr = np.asarray(y)
    y_idx = np.array([classes.index(v) for v in y_arr])

    calib_rows = []
    for i, c in enumerate(classes):
        calib_rows.append({
            "action": c,
            "predicted_mean_prob": float(proba[:, i].mean()),
            "empirical_freq": float((y_arr == c).mean()),
        })

    return EvalResult(
        n=len(y_arr),
        accuracy=accuracy_score(y_arr, pred),
        balanced_accuracy=balanced_accuracy_score(y_arr, pred),
        macro_f1=f1_score(y_arr, pred, average="macro", zero_division=0),
        log_loss=log_loss(y_arr, proba, labels=classes),
        brier=_multiclass_brier(y_idx, proba, len(classes)),
        confusion=confusion_matrix(y_arr, pred, labels=classes),
        labels=classes,
        calibration=pd.DataFrame(calib_rows),
    )


@dataclass
class TrainingReport:
    chosen_model: str
    train_n: int
    val_n: int
    test_n: int
    val_results: dict = field(default_factory=dict)  # nome -> EvalResult
    test_result: EvalResult | None = None
    train_period: tuple[str, str] | None = None
    val_period: tuple[str, str] | None = None
    test_period: tuple[str, str] | None = None


def train_and_evaluate(df: pd.DataFrame) -> tuple[TrainingReport, object]:
    """Split temporal (nunca aleatório — ver `export.temporal_split`),
    treina os 3 modelos candidatos no TREINO, escolhe o melhor por
    `balanced_accuracy` na VALIDAÇÃO, e só então avalia esse escolhido no
    TESTE (uma vez só — teste não participa da escolha do modelo)."""
    df = prepare_dataset(df)
    train_df, val_df, test_df = temporal_split(df)

    factories = _model_factories()
    val_results: dict[str, EvalResult] = {}
    pipelines: dict[str, object] = {}
    for name, factory in factories.items():
        pipeline = _build_pipeline(factory())
        pipeline.fit(train_df[ALL_FEATURES], train_df["action_class"])
        pipelines[name] = pipeline
        val_results[name] = evaluate(pipeline, val_df[ALL_FEATURES], val_df["action_class"])

    chosen_name = max(val_results, key=lambda n: val_results[n].balanced_accuracy)
    chosen_pipeline = pipelines[chosen_name]
    test_result = evaluate(chosen_pipeline, test_df[ALL_FEATURES], test_df["action_class"])

    def _period(sub_df):
        return (str(sub_df["ts"].min()), str(sub_df["ts"].max())) if len(sub_df) else (None, None)

    report = TrainingReport(
        chosen_model=chosen_name,
        train_n=len(train_df), val_n=len(val_df), test_n=len(test_df),
        val_results=val_results, test_result=test_result,
        train_period=_period(train_df), val_period=_period(val_df), test_period=_period(test_df),
    )
    return report, chosen_pipeline


def save_policy(pipeline, path: str) -> None:
    import joblib
    joblib.dump(pipeline, path)


def format_report(report: TrainingReport) -> str:
    lines = ["=== Behavioral Cloning — Personal Policy (Fase 2) ===", ""]
    lines.append(f"Split temporal: train={report.train_n} ({report.train_period[0]} -> {report.train_period[1]})")
    lines.append(f"                val={report.val_n} ({report.val_period[0]} -> {report.val_period[1]})")
    lines.append(f"                test={report.test_n} ({report.test_period[0]} -> {report.test_period[1]})")
    lines.append("")
    lines.append("Validação (escolha do modelo por balanced_accuracy):")
    for name, r in report.val_results.items():
        marker = " <== escolhido" if name == report.chosen_model else ""
        lines.append(
            f"  {name:<22} acc={r.accuracy:.3f} bal_acc={r.balanced_accuracy:.3f} "
            f"macro_f1={r.macro_f1:.3f} log_loss={r.log_loss:.3f} brier={r.brier:.3f}{marker}"
        )
    lines.append("")
    t = report.test_result
    lines.append(f"Teste final ({report.chosen_model}, avaliado uma única vez):")
    lines.append(f"  accuracy={t.accuracy:.3f}  balanced_accuracy={t.balanced_accuracy:.3f}")
    lines.append(f"  macro_f1={t.macro_f1:.3f}  log_loss={t.log_loss:.3f}  brier={t.brier:.3f}")
    lines.append("")
    lines.append("Calibração (prob. média prevista vs. frequência real, no teste):")
    for _, row in t.calibration.iterrows():
        lines.append(f"  {row['action']:<6} previsto={row['predicted_mean_prob']:.3f}  real={row['empirical_freq']:.3f}")
    lines.append("")
    lines.append(f"Matriz de confusão (linhas=real, colunas=previsto) — labels={t.labels}:")
    for label, row in zip(t.labels, t.confusion):
        lines.append(f"  {label:<6} {row.tolist()}")
    return "\n".join(lines)


class PersonalPolicy:
    """Wrapper fino de inferência — `predict_proba`/`recommend` sobre um
    estado (dict), não sobre um DataFrame já preparado."""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def _row(self, state: dict) -> pd.DataFrame:
        row = dict(state)
        if "hero_hand_class" not in row and row.get("hero_cards"):
            try:
                row["hero_hand_class"] = class_of(parse_hand(row["hero_cards"]))
            except (KeyError, IndexError, ValueError):
                row["hero_hand_class"] = None
        for col in ALL_FEATURES:
            row.setdefault(col, None)
        return pd.DataFrame([row])[ALL_FEATURES]

    def predict_proba(self, state: dict) -> dict[str, float]:
        proba = self.pipeline.predict_proba(self._row(state))[0]
        return dict(zip(self.pipeline.classes_, (float(p) for p in proba)))

    def recommend(self, state: dict) -> str:
        probs = self.predict_proba(state)
        return max(probs, key=probs.get)


def load_policy(path: str) -> PersonalPolicy:
    import joblib
    return PersonalPolicy(joblib.load(path))


@lru_cache(maxsize=4)
def load_policy_cached(path: str) -> PersonalPolicy:
    """Mesmo `load_policy`, memoizado por caminho — pro backend (FastAPI)
    não desserializar o pipeline do zero a cada request. `maxsize=4` é
    deliberado: nunca vai ter mais que 1-2 versões de artefato em uso ao
    mesmo tempo num processo, não precisa de cache grande."""
    return load_policy(path)
