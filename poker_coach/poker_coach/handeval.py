"""Avaliador de mãos de poker (5 e 7 cartas) — sem dependências externas.

Extraído de `pushfold/equity.py` para ser compartilhado entre o motor
push/fold (preflop) e o `equity_engine` (pós-flop), sem duplicar a lógica
de avaliação de mão. Mantém o mesmo comportamento/assinaturas de antes —
`pushfold/equity.py` reexporta estes símbolos por compatibilidade.
"""
from __future__ import annotations

import itertools

RANKS = "23456789TJQKA"
RANK_VALUE = {r: i for i, r in enumerate(RANKS, start=2)}
SUITS = "shdc"

Card = tuple[int, str]


def parse_card(s: str) -> Card:
    s = s.strip()
    rank, suit = s[0].upper(), s[1].lower()
    return RANK_VALUE[rank], suit


def parse_hand(s: str) -> list[Card]:
    """'Kh 2h' / 'Kh2h' -> [(13,'h'), (2,'h')]"""
    s = s.replace(",", " ").strip()
    parts = s.split() if " " in s else [s[i:i + 2] for i in range(0, len(s), 2)]
    return [parse_card(p) for p in parts]


def full_deck() -> list[Card]:
    return [(r, s) for r in RANK_VALUE.values() for s in SUITS]


def _check_straight(ranks5: list[int]) -> tuple[bool, int]:
    s = set(ranks5)
    if len(s) != 5:
        return False, 0
    if s == {14, 2, 3, 4, 5}:
        return True, 5  # "roda": 5-alta
    mx, mn = max(s), min(s)
    if mx - mn == 4:
        return True, mx
    return False, 0


def hand_rank5(cards: list[Card]) -> tuple:
    """Retorna uma tupla comparável (maior = mão melhor)."""
    ranks = sorted((r for r, _ in cards), reverse=True)
    is_flush = len({s for _, s in cards}) == 1
    is_straight, top = _check_straight(ranks)

    counts: dict[int, int] = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    groups = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    pattern = tuple(c for _, c in groups)
    ordered = tuple(r for r, _ in groups)

    if is_straight and is_flush:
        return (8, top)
    if pattern == (4, 1):
        return (7,) + ordered
    if pattern == (3, 2):
        return (6,) + ordered
    if is_flush:
        return (5,) + tuple(ranks)
    if is_straight:
        return (4, top)
    if pattern == (3, 1, 1):
        return (3,) + ordered
    if pattern == (2, 2, 1):
        return (2,) + ordered
    if pattern == (2, 1, 1, 1):
        return (1,) + ordered
    return (0,) + tuple(ranks)


def best_of_7(cards7: list[Card]) -> tuple:
    return max(hand_rank5(list(c)) for c in itertools.combinations(cards7, 5))


def best_of_n(cards: list[Card]) -> tuple:
    """Generalização de `best_of_7` pra qualquer nº de cartas >= 5 (ex.: 6
    cartas = hole + flop+turn, usado pelo equity_engine pra avaliar mãos
    parciais sem esperar o river)."""
    if len(cards) < 5:
        raise ValueError(f"precisa de pelo menos 5 cartas, recebeu {len(cards)}")
    if len(cards) == 5:
        return hand_rank5(list(cards))
    return max(hand_rank5(list(c)) for c in itertools.combinations(cards, 5))
