"""Motor de ICM (Malmuth-Harville) + Risk Premium + push/fold ajustado
por ICM.

Limitação FUNDAMENTAL, comunicada na UI, não escondida: ICM precisa dos
stacks de TODOS os jogadores restantes no torneio + a estrutura de
premiação. A hand history só mostra os jogadores da SUA mesa, nunca o
campo inteiro (um MTT tem várias mesas). Por isso essa análise só faz
sentido quando a mesa da mão JÁ É a mesa final (aí "jogadores da mesa"
== "jogadores do torneio") — fora disso o número seria inventado. A
página de ICM exige confirmação explícita + estrutura de premiação
antes de calcular qualquer coisa (ver app_pages/icm.py).

Malmuth-Harville: modelo padrão (não é o único, mas é o que toda
calculadora de push/fold leve usa) — assume que a probabilidade de cada
jogador terminar em cada posição é proporcional ao stack, recursivamente
removendo quem já "ganhou" aquela posição. Enviesado em campos muito
grandes/com stacks muito díspares (super-estima o favorito), mas é o
padrão da indústria pra mesa final/heads-up de MTT pequeno.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=200_000)
def _icm_equity_cached(stacks: tuple[int, ...], payouts: tuple[float, ...]) -> tuple[float, ...]:
    n = len(stacks)
    if n == 0:
        return ()
    if n == 1:
        return (payouts[0] if payouts else 0.0,)
    total = sum(stacks)
    if total <= 0:
        return tuple(0.0 for _ in stacks)
    first_prize = payouts[0] if payouts else 0.0
    rest_payouts = payouts[1:] if len(payouts) > 1 else ()
    equities = [0.0] * n
    for i in range(n):
        if stacks[i] <= 0:
            continue
        p_first = stacks[i] / total
        remaining_stacks = stacks[:i] + stacks[i + 1:]
        sub = _icm_equity_cached(remaining_stacks, rest_payouts)
        equities[i] += p_first * first_prize
        for j in range(n - 1):
            idx = j if j < i else j + 1
            equities[idx] += p_first * sub[j]
    return tuple(equities)


def icm_equity(stacks: list[int], payouts: list[float]) -> list[float]:
    """$EV de cada jogador dado o vetor de stacks (em fichas) e a
    estrutura de premiação (payouts[0]=1º lugar, [1]=2º, ...; lugares
    não pagos ficam de fora ou como 0). Padroniza o tamanho da lista de
    prêmios pro tamanho do campo — sobra vira 0 (bolha)."""
    n = len(stacks)
    padded = (list(payouts) + [0.0] * n)[:n]
    return list(_icm_equity_cached(tuple(stacks), tuple(padded)))


def risk_premium_pct(stacks: list[int], payouts: list[float], hero_idx: int) -> float:
    """Quanto a SOBREVIVÊNCIA do herói vale a mais em $ do que a fatia
    proporcional de fichas sugere (pontos percentuais) — mede o quanto
    o ICM "puxa" a decisão pro lado conservador em relação ao chip EV
    puro. 0 = ICM não muda nada (ex.: campo bem cedo, stacks parecidos);
    valores altos = bolha/mesa final, jogue mais tight que chip EV manda."""
    total_chips = sum(stacks)
    if total_chips <= 0:
        return 0.0
    equities = icm_equity(stacks, payouts)
    total_prize = sum(equities)
    if total_prize <= 0:
        return 0.0
    chip_share = stacks[hero_idx] / total_chips
    icm_share = equities[hero_idx] / total_prize
    return round((chip_share - icm_share) * 100, 2)


def push_fold_icm_ev(stacks: list[int], payouts: list[float], hero_idx: int,
                      villain_idx: int, effective_stack: int, pot_dead: int,
                      equity_vs_call: float, p_call: float) -> tuple[float, float]:
    """$EV de dar fold vs empurrar, sob ICM, nesse spot específico.

    `stacks` = stacks de TODOS os jogadores restantes na mão (não só
    herói/vilão), JÁ descontando o que cada um postou até aqui (mesma
    convenção do motor de chip EV em pushfold/analyze.py). `pot_dead` =
    dinheiro já na mesa antes do push. `effective_stack` = min(herói,
    vilão) restante. `equity_vs_call`/`p_call` vêm do MESMO solve de
    Nash em chip EV do motor de Push/Fold — ver limitação no docstring
    do módulo (a range de call da BB não é re-resolvida sob ICM, isso
    ficaria muito mais caro; assume-se que a range de call não muda
    muito entre os dois modelos, só a decisão do HERÓI é reavaliada).

    Retorna (icm_ev_fold, icm_ev_push) em $.
    """
    icm_ev_fold = icm_equity(stacks, payouts)[hero_idx]  # ficar como está = "fold"

    stacks_fold_through = list(stacks)
    stacks_fold_through[hero_idx] += pot_dead
    ev_uncontested = icm_equity(stacks_fold_through, payouts)[hero_idx]

    stacks_win = list(stacks)
    stacks_win[hero_idx] += pot_dead + effective_stack
    stacks_win[villain_idx] -= effective_stack
    ev_win = icm_equity(stacks_win, payouts)[hero_idx]

    stacks_lose = list(stacks)
    stacks_lose[hero_idx] -= effective_stack
    stacks_lose[villain_idx] += pot_dead + effective_stack
    ev_lose = icm_equity(stacks_lose, payouts)[hero_idx]

    icm_ev_push = (1 - p_call) * ev_uncontested + p_call * (
        equity_vs_call * ev_win + (1 - equity_vs_call) * ev_lose)

    return icm_ev_fold, icm_ev_push
