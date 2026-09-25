"""Fase 4 do plano de RL — treino do agente de Push/Fold via PPO.

Roda local (CPU) pra validar o pipeline rápido, ou no Colab (GPU) pro
treino "de verdade" com mais timesteps — ver `notebooks/01_pushfold_rl.ipynb`.
O notebook existe porque foi pedido explicitamente (plano AI Pro do
usuário), ainda que esse problema específico (observação 3-dim, 2 ações)
não precise de GPU de fato pra treinar rápido — dito isso claramente, não
escondido, na mesma linha do que já foi avisado antes nesta sessão sobre
GPU vs CPU-bound.

LACUNA CONHECIDA, não escondida: a seção 14 do plano pede BC warm-start
(clonar o comportamento REAL do hero — Fase 2 — antes do PPO). NÃO está
implementado nesta versão. Fazer isso direito exige transplantar pesos
pré-treinados pra dentro da rede de política do SB3
(`model.policy.mlp_extractor`/`action_net`) ou usar a lib `imitation`
(BC + integração nativa com SB3 — `pip install imitation`, treinar
`imitation.algorithms.bc.BC` nos pares (state, action) de `preflop_open`
do dataset, usar `bc_trainer.policy` como policy inicial do PPO). Ficou
de fora por risco de fragilidade sob prazo apertado nesta sessão — o PPO
abaixo treina do zero (init padrão do SB3), não a partir da Personal
Policy da Fase 2.

CUIDADO COM LEAKAGE (seção 16 do plano — ver também `pushfold_env.py`):
reward, vilão e avaliação usam o MESMO motor Nash. Isso valida a
infraestrutura de RL (ambiente, reward, pipeline de treino/avaliação),
não é uma alegação de estratégia superior a Nash.
"""
from __future__ import annotations

from dataclasses import dataclass


def train_ppo(*, total_timesteps: int = 20_000, n_envs: int = 4, seed: int = 0,
              state_samples: list[tuple[float, float]] | None = None,
              net_arch: list[int] | None = None, env_cls=None, device: str = "cpu"):
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env

    from .pushfold_env import PushFoldOpenEnv

    env_cls = env_cls or PushFoldOpenEnv

    def _make():
        return env_cls(state_samples=state_samples, seed=seed)

    vec_env = make_vec_env(_make, n_envs=n_envs, seed=seed)
    model = PPO(
        "MlpPolicy", vec_env, verbose=0, seed=seed, device=device,
        policy_kwargs=dict(net_arch=net_arch or [32, 32]),
    )
    model.learn(total_timesteps=total_timesteps)
    return model


def agent_predict_fn(model):
    def _predict(obs):
        action, _ = model.predict(obs, deterministic=True)
        return int(action)
    return _predict


def save_model(model, path: str) -> None:
    model.save(path)


def load_model(path: str):
    from stable_baselines3 import PPO
    return PPO.load(path)


@dataclass
class TrainingRunReport:
    total_timesteps: int
    benchmark_before: object
    benchmark_after: object


def train_and_benchmark(*, total_timesteps: int = 20_000, seed: int = 0,
                         state_samples: list[tuple[float, float]] | None = None,
                         grid_points: int = 15, env_cls=None,
                         device: str = "cpu") -> tuple[TrainingRunReport, object]:
    """Treina e avalia contra o MESMO baseline aleatório antes/depois —
    prova que o treino de fato converge em direção ao Nash, não só reporta
    um número solto. `env_cls` (padrão `PushFoldOpenEnv`) também aceita
    `PushFoldFacingShoveEnv` — mesma função serve pros dois lados do
    equilíbrio, não precisa duplicar. `device` default `"cpu"`: rede
    minúscula (`net_arch=[32,32]`) — overhead de transferência CPU↔GPU
    supera o ganho (aviso do próprio SB3), CPU é mais rápido aqui."""
    import numpy as np

    from .pushfold_env import PushFoldOpenEnv, evaluate_against_nash

    env_cls = env_cls or PushFoldOpenEnv
    rng = np.random.default_rng(seed)

    def random_predict(obs):
        return int(rng.integers(2))

    before = evaluate_against_nash(env_cls, random_predict, grid_points=grid_points, seed=seed)

    model = train_ppo(total_timesteps=total_timesteps, seed=seed, state_samples=state_samples,
                       env_cls=env_cls, device=device)
    after = evaluate_against_nash(env_cls, agent_predict_fn(model), grid_points=grid_points, seed=seed)

    report = TrainingRunReport(total_timesteps=total_timesteps, benchmark_before=before, benchmark_after=after)
    return report, model


def format_training_report(report: TrainingRunReport) -> str:
    b, a = report.benchmark_before, report.benchmark_after
    return "\n".join([
        "=== Push/Fold PPO — treino + benchmark (Fase 4) ===", "",
        f"total_timesteps={report.total_timesteps}", "",
        "ANTES do treino (política aleatória, baseline):",
        f"  agreement={b.agreement_pct}%  mean_ev_gap={b.mean_ev_gap}  "
        f"median={b.median_ev_gap}  worst={b.worst_ev_gap}",
        f"  clear: {b.clear_agreement_pct}% (n={b.clear_n})  "
        f"borderline: {b.borderline_agreement_pct}% (n={b.borderline_n})",
        "",
        "DEPOIS do treino (agente PPO):",
        f"  agreement={a.agreement_pct}%  mean_ev_gap={a.mean_ev_gap}  "
        f"median={a.median_ev_gap}  worst={a.worst_ev_gap}",
        f"  clear: {a.clear_agreement_pct}% (n={a.clear_n})  "
        f"borderline: {a.borderline_agreement_pct}% (n={a.borderline_n})",
        "",
        "Lembrete: reward/vilão/avaliação usam o MESMO Nash — isso mede se "
        "a infraestrutura de RL converge pra uma aproximação do equilíbrio "
        "já conhecido, não uma estratégia nova (ver docstring do módulo e "
        "de pushfold_env.py).",
    ])
