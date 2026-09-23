"""Fase 4 do plano de RL — ambiente Gymnasium de Push/Fold.

Import de `gymnasium` é lazy/guardado — este módulo só é importado por
quem for treinar/avaliar RL de verdade (notebook Colab ou script local),
nunca pelo FastAPI (ver seção 18 do plano: não misturar RL com o backend).

Reaproveita `pushfold/nash.py` e `pushfold/equity.py` como fonte de
reward E de vilão — não reimplementa equilíbrio. Usa especificamente
`nash.ev_grid`/`nash.call_ev_grid` (grid pré-computado contra a matriz de
169 classes) em vez de `nash.ev_shove_bb` (Monte Carlo ao vivo com cartas
exatas, usado em `context.py` pra decisão real de dinheiro): treino de RL
faz muitos milhares de passos, então precisão de matriz + cache já
validado em produção (`pushfold/analyze._cached_solve`) é a troca certa
de velocidade — a mesma classe de troca já documentada em `export.py`
pro `--equity-iterations`.

"Self-play" aqui é o hero (agente aprendendo) contra um vilão que joga a
RANGE DE EQUILÍBRIO do próprio Nash pro (effective_bb, pot_bb) do
episódio — não os dois lados aprendendo ao mesmo tempo (isso é upgrade
futuro, ver seção 20 do plano/roadmap V5 em diante).

REWARD — nunca win=+1/loss=-1 (seção 13 do plano):
- `PushFoldOpenEnv` (abertura): fold=0.0 (baseline sem custo afundado,
  mesma convenção de `ev_engine.py`), push=`ev_grid[hand_class]` (chip-EV
  contra a call range de equilíbrio, COM termo de fold equity).
- `PushFoldFacingShoveEnv` (pagando all-in já na mesa): fold=0.0,
  call=`call_ev_grid[hand_class]` (chip-EV contra a range de shove do
  vilão, SEM fold equity — quem decide é o herói, o vilão já empurrou).

CUIDADO COM LEAKAGE DO BENCHMARK (seção 16 do plano, não escondido): o
MESMO motor Nash desenha o vilão, calcula o reward e serve de referência
de avaliação (`evaluate_against_nash` abaixo). Um agente treinado aqui
está aprendendo uma APROXIMAÇÃO da política de equilíbrio chip-EV já
conhecida — o objetivo é validar a infraestrutura de RL (ambiente,
reward, pipeline de treino/avaliação), não alegar que o agente descobriu
uma estratégia superior a Nash.
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    import gymnasium as gym
    import numpy as np
    from gymnasium import spaces
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "pushfold_env precisa de gymnasium/numpy (pip install -r requirements-rl.txt "
        "no mesmo venv). Não é dependência do backend principal, só do pipeline de RL."
    ) from exc

from ..pushfold import analyze as pf_analyze
from ..pushfold import equity as pf_equity
from ..pushfold import nash as pf_nash


def _round_for_cache(effective_bb: float, pot_bb: float) -> tuple[float, float]:
    """Mesmo arredondamento de `pushfold/analyze.py::_cached_solve` — pra
    de fato bater no cache já aquecido em produção, não criar um novo."""
    return round(effective_bb * 2) / 2, round(pot_bb * 4) / 4


def sample_states_from_dataset(df, context_type: str) -> list[tuple[float, float]]:
    """Calibra a distribuição de (effective_bb, pot_bb) do ambiente a
    partir de spots REAIS do dataset da Fase 1 (`rl/export.py`), em vez
    de só uniforme sintético — filtra por `context_type` (ex.
    "preflop_open" pro opener, "preflop_facing_allin" pro facing-shove)."""
    sub = df[df["context_type"] == context_type]
    sub = sub.dropna(subset=["effective_stack_bb", "pot_before_action_bb"])
    return list(zip(sub["effective_stack_bb"].astype(float), sub["pot_before_action_bb"].astype(float)))


class _BasePushFoldEnv(gym.Env):
    """Base comum — estado (força de mão normalizada + effective_bb + pot_bb
    normalizados), sorteio de spot, cache do solve Nash. Subclasses só
    diferem na função de EV (`_ev_for_aggressive_action`) e no rótulo da
    ação agressiva ("push" vs "call")."""

    metadata = {"render_modes": []}
    aggressive_label: str = "push"

    def __init__(self, *, bb_min: float = 5.0, bb_max: float = 40.0,
                 default_pot_bb: float = 1.5,
                 state_samples: list[tuple[float, float]] | None = None,
                 seed: int | None = None):
        super().__init__()
        self.bb_min, self.bb_max, self.default_pot_bb = bb_min, bb_max, default_pot_bb
        self.state_samples = state_samples
        self.ranking = pf_equity.build_ranking()
        self.matrix = pf_equity.build_class_matrix()
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(3,), dtype=np.float32)
        self.action_space = spaces.Discrete(2)  # 0=fold, 1=ação agressiva (push/call)
        self._np_rng = np.random.default_rng(seed)

        self._hand_class: str | None = None
        self._effective_bb: float | None = None
        self._pot_bb: float | None = None
        self._nash: pf_nash.NashResult | None = None
        self._ev_grid: dict[str, float] | None = None

    def _solve(self, effective_bb: float, pot_bb: float) -> pf_nash.NashResult:
        eb, pb = _round_for_cache(effective_bb, pot_bb)
        return pf_analyze._cached_solve(eb, pb)

    def _ev_grid_for(self, effective_bb: float, pot_bb: float, result: pf_nash.NashResult) -> dict[str, float]:
        raise NotImplementedError

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        rng = self._np_rng if seed is None else np.random.default_rng(seed)
        if self.state_samples:
            idx = int(rng.integers(len(self.state_samples)))
            eff, pot = self.state_samples[idx]
        else:
            eff, pot = float(rng.uniform(self.bb_min, self.bb_max)), self.default_pot_bb
        self._effective_bb, self._pot_bb = float(eff), float(pot)
        self._hand_class = self.ranking[int(rng.integers(len(self.ranking)))]
        self._nash = self._solve(self._effective_bb, self._pot_bb)
        self._ev_grid = self._ev_grid_for(self._effective_bb, self._pot_bb, self._nash)
        info = {
            "hand_class": self._hand_class,
            "effective_bb": self._effective_bb,
            "pot_bb": self._pot_bb,
        }
        return self._obs(), info

    def _obs(self) -> "np.ndarray":
        rank_idx = self.ranking.index(self._hand_class)
        strength = 1.0 - rank_idx / (len(self.ranking) - 1)  # ranking[0] = mão mais forte (AA)
        return np.array([
            strength,
            min(self._effective_bb / 100.0, 1.0),
            min(self._pot_bb / 5.0, 1.0),
        ], dtype=np.float32)

    def step(self, action: int):
        ev_aggressive = float(self._ev_grid[self._hand_class])
        reward = ev_aggressive if action == 1 else 0.0
        # Referência = sinal do EV (maximiza EV), NÃO "está na shove_classes
        # do equilíbrio de fictitious play" — as duas noções podem discordar
        # em spots de fronteira (mesmo fenômeno já documentado em
        # context.py: EV ao vivo com cartas exatas vs. should_shove() da
        # matriz de classe podem discordar). Usar a range de equilíbrio
        # aqui deixava o benchmark reportar `mean_ev_gap` NEGATIVO — uma
        # "referência" pior que a ação do próprio agente é uma referência
        # errada pra essa finalidade (medir EV gap), não um resultado real.
        nash_recommends_aggressive = ev_aggressive > 0
        info = {
            "hand_class": self._hand_class,
            "effective_bb": self._effective_bb,
            "pot_bb": self._pot_bb,
            "reference_action": self.aggressive_label if nash_recommends_aggressive else "fold",
            f"ev_{self.aggressive_label}_bb": ev_aggressive,
        }
        # episódio de 1 decisão só — cada reset() é um spot novo e
        # independente (bandit contextual), não uma sequência de mão.
        terminated, truncated = True, False
        return self._obs(), reward, terminated, truncated, info


class PushFoldOpenEnv(_BasePushFoldEnv):
    """Spot de ABERTURA preflop — herói decide push ou fold, ninguém
    apostou ainda (mesmo escopo do Nash isolado, `context_type` ==
    "preflop_open" no dataset da Fase 1). Ação 0=fold, 1=push."""

    aggressive_label = "push"

    def _ev_grid_for(self, effective_bb, pot_bb, result):
        grid, _ = pf_nash.ev_grid(effective_bb, pot_bb, self.ranking, self.matrix, result=result)
        return grid


class PushFoldFacingShoveEnv(_BasePushFoldEnv):
    """Spot de PAGAR um all-in já na mesa — herói decide call ou fold
    (`context_type` == "preflop_facing_allin"/"preflop_multiway_facing_allin"
    no dataset, escopo heads-up aqui). Ação 0=fold, 1=call."""

    aggressive_label = "call"

    def _ev_grid_for(self, effective_bb, pot_bb, result):
        grid, _ = pf_nash.call_ev_grid(effective_bb, pot_bb, self.ranking, self.matrix, result=result)
        return grid


@dataclass
class BenchmarkResult:
    """As 3 avaliações pedidas (seção 15 do plano) — nunca só "agreement
    >= 95%". `clear_n`/`borderline_n` separam decisões perto da fronteira
    fold/push (|ev| pequeno) das claras, porque errar uma decisão
    indiferente não é o mesmo tipo de erro que errar uma clara."""
    n: int
    agreement_pct: float
    mean_ev_gap: float
    median_ev_gap: float
    worst_ev_gap: float
    clear_n: int
    clear_agreement_pct: float
    borderline_n: int
    borderline_agreement_pct: float


def evaluate_against_nash(env_cls, agent_predict, *, grid_points: int | None = None,
                           borderline_threshold_bb: float = 0.5, seed: int = 0) -> BenchmarkResult:
    """Avalia `agent_predict(obs) -> 0|1` numa grade determinística
    (effective_bb x hand_class), NUNCA nos episódios de treino — grade
    própria, held-out por construção (não é um split de dados, é gerar
    estados nunca vistos exatamente com essa combinação exata na mesma
    sequência de treino). Mede exatamente as 3 métricas pedidas:
    A) agreement com a ação de referência Nash; B) EV gap (reward que o
    agente teria vs o EV da ação de referência); C) generalização (a
    própria grade, que nunca é usada como episódio de treino)."""
    ranking = pf_equity.build_ranking()
    env = env_cls(bb_min=5, bb_max=40)
    stacks = np.linspace(5, 40, grid_points or 15)

    agreements, ev_gaps = [], []
    clear_ok = clear_n = borderline_ok = borderline_n = 0
    for eff in stacks:
        result = env._solve(float(eff), env.default_pot_bb)
        grid = env._ev_grid_for(float(eff), env.default_pot_bb, result)
        for cls in ranking:
            rank_idx = ranking.index(cls)
            strength = 1.0 - rank_idx / (len(ranking) - 1)
            obs = np.array([strength, min(eff / 100.0, 1.0), min(env.default_pot_bb / 5.0, 1.0)], dtype=np.float32)
            action = agent_predict(obs)
            # Referência = sinal do EV, não a range de equilíbrio do
            # fictitious play (ver comentário em _BasePushFoldEnv.step) —
            # garante que a referência nunca é pior que a própria ação do
            # agente (gap sempre >= 0).
            ref_action = 1 if grid[cls] > 0 else 0
            agree = action == ref_action
            agreements.append(agree)

            ev_aggressive = grid[cls]
            ev_agent = ev_aggressive if action == 1 else 0.0
            ev_ref = ev_aggressive if ref_action == 1 else 0.0
            gap = ev_ref - ev_agent
            ev_gaps.append(gap)

            is_borderline = abs(ev_aggressive) < borderline_threshold_bb
            if is_borderline:
                borderline_n += 1
                borderline_ok += int(agree)
            else:
                clear_n += 1
                clear_ok += int(agree)

    ev_arr = np.array(ev_gaps)
    n = len(agreements)
    return BenchmarkResult(
        n=n,
        agreement_pct=round(100 * sum(agreements) / n, 2),
        mean_ev_gap=round(float(ev_arr.mean()), 4),
        median_ev_gap=round(float(np.median(ev_arr)), 4),
        worst_ev_gap=round(float(ev_arr.max()), 4),
        clear_n=clear_n,
        clear_agreement_pct=round(100 * clear_ok / clear_n, 2) if clear_n else 0.0,
        borderline_n=borderline_n,
        borderline_agreement_pct=round(100 * borderline_ok / borderline_n, 2) if borderline_n else 0.0,
    )
