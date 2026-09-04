"""Solver de push/fold Nash (Chip EV), heads-up: herói empurra all-in,
único vilão decide call/fold.

Simplificação assumida (documentada): em uma mão N-max, o vilão modelado
é a BB (normalmente quem fecha a ação e tem a melhor odds — o "pior caso"
mais restritivo para o herói). Jogadores intermediários que também
poderiam pagar não entram no solve; isso é uma aproximação padrão de
calculadoras leves de push/fold para spots de abertura (não é um solve
multiway/ICM completo — isso fica pro roadmap com o motor de ICM).

Fórmula de EV (chip EV, relativa a "herói dá fold agora" = 0), com:
  pot   = dinheiro morto na mesa antes do all-in (blinds + antes já postados)
  eff   = min(stack restante do herói, stack restante do vilão)  [em BB]
  eq    = equity do herói contra a range de call do vilão

  EV_shove = P(fold) * pot + P(call) * (eq * (pot + 2*eff) - eff)

Ambos os lados (herói decidindo empurrar, vilão decidindo pagar) usam a
mesma fórmula (é simétrica: o vilão "empurra" chips pra dentro pagando).
Resolvido por iteração de ponto fixo com amortecimento (média entre a
range antiga e a nova) até estabilizar — não é uma prova formal de
convergência, mas é o método padrão usado por calculadoras de push/fold
leves e converge bem na prática para esse problema (utilidades monótonas
em força de mão).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import equity as eq


@dataclass
class NashResult:
    effective_bb: float
    pot_bb: float
    shove_classes: list[str]
    call_classes: list[str]
    shove_pct: float
    call_pct: float
    iterations_run: int

    def should_shove(self, hand_class: str) -> bool:
        return hand_class in self.shove_classes


def ev_shove_bb(hero_cards: list[tuple[int, str]], call_range: list[str],
                 effective_bb: float, pot_bb: float, call_pct: float,
                 trials_per_class: int = 300, seed: int | None = None) -> tuple[float, float]:
    """Retorna (ev_bb, equity_vs_call_range) do all-in do herói com essas
    cartas exatas, dado que o vilão paga com `call_range` uma fração
    `call_pct` (0..1) das vezes."""
    equity_vs_range = eq.equity_hand_vs_range(hero_cards, call_range,
                                               trials_per_class=trials_per_class, seed=seed)
    p_fold = 1 - call_pct
    ev = p_fold * pot_bb + call_pct * (equity_vs_range * (pot_bb + 2 * effective_bb) - effective_bb)
    return ev, equity_vs_range


def solve(effective_bb: float, pot_bb: float, ranking: list[str] | None = None,
          matrix: dict[str, float] | None = None,
          iterations: int = 60, burn_in: int = 20) -> NashResult:
    """Resolve o equilíbrio push (herói) / call (vilão) por *fictitious
    play*: iteração de melhor resposta, com o resultado final sendo a
    MÉDIA NO TEMPO de quantas iterações cada classe apareceu na range
    (não a última iteração isolada).

    Por quê: a iteração de melhor resposta "crua" (usar só a última
    resposta pra alimentar a próxima) entra num ciclo de período 2 nesse
    problema — herói e vilão ficam se sobre-ajustando um ao outro e nunca
    param (testado e confirmado empiricamente). Fictitious play resolve
    isso porque, embora a sequência de melhores respostas oscile, a MÉDIA
    no tempo converge para o equilíbrio (Robinson, 1951, pra jogos de
    soma zero de 2 jogadores — que é exatamente a estrutura aqui: o que
    o herói ganha em EV, o vilão perde, e vice-versa).

    effective_bb: min(stack restante do herói, stack restante do vilão), em BB.
    pot_bb: dinheiro morto (blinds+antes já postados) antes do all-in, em BB.
    """
    if ranking is None:
        ranking = eq.build_ranking()
    if matrix is None:
        matrix = eq.build_class_matrix()

    shove_classes = list(ranking)  # chute inicial: herói empurra tudo
    call_counts = dict.fromkeys(ranking, 0)
    shove_counts = dict.fromkeys(ranking, 0)
    n_avg = 0

    it = 0
    for it in range(1, iterations + 1):
        # resposta ótima do vilão à range de shove atual do herói:
        # paga se eq*(pot+2*eff) - eff >= 0 (o all-in do herói já está na mesa).
        new_call_classes = [
            cls for cls in ranking
            if eq.equity_class_vs_range(cls, shove_classes, matrix) * (pot_bb + 2 * effective_bb)
            - effective_bb >= 0
        ]
        p_call = eq.range_combo_pct(new_call_classes) / 100

        # resposta ótima do herói à nova range de call do vilão.
        new_shove_classes = [
            cls for cls in ranking
            if (1 - p_call) * pot_bb + p_call * (
                eq.equity_class_vs_range(cls, new_call_classes, matrix) * (pot_bb + 2 * effective_bb)
                - effective_bb
            ) >= 0
        ]

        if it > burn_in:
            for c in new_call_classes:
                call_counts[c] += 1
            for c in new_shove_classes:
                shove_counts[c] += 1
            n_avg += 1

        shove_classes = new_shove_classes  # alimenta a próxima iteração

    if n_avg == 0:  # iterations <= burn_in: usa a última resposta crua
        call_classes = new_call_classes
        final_shove = new_shove_classes
    else:
        call_classes = [c for c, n in call_counts.items() if n / n_avg >= 0.5]
        final_shove = [c for c, n in shove_counts.items() if n / n_avg >= 0.5]

    return NashResult(
        effective_bb=effective_bb, pot_bb=pot_bb,
        shove_classes=final_shove, call_classes=call_classes,
        shove_pct=eq.range_combo_pct(final_shove),
        call_pct=eq.range_combo_pct(call_classes), iterations_run=it,
    )


def ev_grid(effective_bb: float, pot_bb: float, ranking: list[str] | None = None,
            matrix: dict[str, float] | None = None,
            result: NashResult | None = None) -> tuple[dict[str, float], NashResult]:
    """EV de empurrar CADA uma das 169 classes (não só a decisão binária
    push/fold) contra a range de call de equilíbrio — o grid 13x13
    completo (tipo ICMizer/HRC), não só uma tabela fold/shove/raise %.
    Usa a matriz rápida (mesma precisão do resto do app, sem MC ao vivo).
    """
    if ranking is None:
        ranking = eq.build_ranking()
    if matrix is None:
        matrix = eq.build_class_matrix()
    if result is None:
        result = solve(effective_bb, pot_bb, ranking, matrix)

    p_call = result.call_pct / 100
    grid = {}
    for cls in ranking:
        equity_vs_range = eq.equity_class_vs_range(cls, result.call_classes, matrix)
        grid[cls] = (1 - p_call) * pot_bb + p_call * (
            equity_vs_range * (pot_bb + 2 * effective_bb) - effective_bb)
    return grid, result
