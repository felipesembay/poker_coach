"""Testes de poker_coach/rl/pushfold_env.py (Fase 4).

Cobre as regras explícitas do plano: reward é EV (nunca win/loss),
vilão joga a range de equilíbrio do próprio Nash, avaliação tem as 3
métricas pedidas (agreement, EV gap, generalização) com N sempre visível,
e o sanity check mais importante — uma política ALEATÓRIA tem que ficar
perto de 50% de concordância (prova que a comparação binária não tá
enviesada)."""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

pytest.importorskip("gymnasium")
from poker_coach.rl.pushfold_env import (  # noqa: E402
    PushFoldFacingShoveEnv,
    PushFoldOpenEnv,
    evaluate_against_nash,
)


@pytest.mark.parametrize("env_cls", [PushFoldOpenEnv, PushFoldFacingShoveEnv])
def test_reset_returns_valid_observation(env_cls):
    env = env_cls(seed=0)
    obs, info = env.reset(seed=1)
    assert obs.shape == (3,)
    assert env.observation_space.contains(obs)
    assert 0 < info["effective_bb"]
    assert info["hand_class"] in env.ranking


@pytest.mark.parametrize("env_cls", [PushFoldOpenEnv, PushFoldFacingShoveEnv])
def test_fold_action_always_has_zero_reward(env_cls):
    """Reward nunca é win=+1/loss=-1 — fold é sempre EV=0 (sem custo
    afundado), igual à convenção de ev_engine.py."""
    env = env_cls(seed=0)
    for seed in range(5):
        env.reset(seed=seed)
        _obs, reward, terminated, truncated, _info = env.step(0)
        assert reward == 0.0
        assert terminated is True
        assert truncated is False


@pytest.mark.parametrize("env_cls", [PushFoldOpenEnv, PushFoldFacingShoveEnv])
def test_aggressive_action_reward_matches_nash_grid(env_cls):
    """Reward da ação agressiva (push/call) é exatamente o EV do grid
    Nash pra essa classe de mão — não é inventado, vem do motor existente."""
    env = env_cls(seed=0)
    env.reset(seed=2)
    hand_class = env._hand_class
    expected = env._ev_grid[hand_class]
    _obs, reward, *_ = env.step(1)
    assert reward == pytest.approx(expected)


def test_state_samples_calibration_restricts_sampled_spots():
    samples = [(10.0, 1.5), (20.0, 1.5)]
    env = PushFoldOpenEnv(state_samples=samples, seed=0)
    seen = set()
    for seed in range(20):
        _obs, info = env.reset(seed=seed)
        seen.add((info["effective_bb"], info["pot_bb"]))
    assert seen <= {(10.0, 1.5), (20.0, 1.5)}


def test_random_policy_gets_close_to_50pct_agreement():
    """Sanity check mais importante do ambiente: se a comparação binária
    contra a referência Nash estiver enviesada, uma política aleatória
    NÃO ficaria perto de 50%."""
    rng = np.random.default_rng(0)

    def random_predict(obs):
        return int(rng.integers(2))

    result = evaluate_against_nash(PushFoldOpenEnv, random_predict, grid_points=10)
    assert 40 <= result.agreement_pct <= 60


def test_evaluate_against_nash_gap_never_negative_even_for_adversarial_policy():
    """Regressão: usar shove_classes/call_classes (range de equilíbrio do
    fictitious play) como referência podia dar mean_ev_gap NEGATIVO,
    porque a range de equilíbrio pode discordar do sinal exato do EV nos
    spots de fronteira (mesmo fenômeno documentado em context.py). Uma
    "referência" pior que a ação de um agente ruim não é uma referência
    válida — o fix usa o sinal do EV, que garante gap >= 0 sempre."""
    def always_fold(obs):
        return 0

    def always_push(obs):
        return 1

    for env_cls in (PushFoldOpenEnv, PushFoldFacingShoveEnv):
        for policy in (always_fold, always_push):
            result = evaluate_against_nash(env_cls, policy, grid_points=15)
            assert result.mean_ev_gap >= -1e-9
            assert result.median_ev_gap >= -1e-9
            assert result.worst_ev_gap >= -1e-9


def test_evaluate_against_nash_reports_all_required_fields():
    """Seção 15 do plano: nunca só agreement — precisa das 3 métricas e
    da separação clara/borderline."""
    def always_push(obs):
        return 1

    result = evaluate_against_nash(PushFoldOpenEnv, always_push, grid_points=5)
    assert result.n > 0
    assert 0 <= result.agreement_pct <= 100
    assert result.clear_n + result.borderline_n == result.n
    assert result.mean_ev_gap >= 0  # gap nunca negativo (referência é sempre ótima ou igual)
    assert result.median_ev_gap >= 0
    assert result.worst_ev_gap >= result.mean_ev_gap - 1e-9
