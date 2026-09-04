"""Avaliador de mãos e cálculo de equity preflop all-in (Monte Carlo).

Sem dependências externas — implementação própria de:
- avaliador de mão de 5 cartas (categoria + desempate)
- melhor mão de 7 cartas (2 hole + 5 board)
- equity hand-vs-hand e hand-vs-range via simulação Monte Carlo
- ranking dos 169 tipos de mão inicial por força (equity vs mão aleatória),
  usado para construir ranges "top X%" de forma reprodutível — não é uma
  tabela decorada, é calculada por este mesmo motor.

Limitação assumida (documentada, não escondida): ranges usam UMA combinação
representativa por classe (ex.: "AKs" -> Ah Kh) em vez de expandir todas as
combinações (4 para suited, 12 para offsuit, 6 para pares). Isso é uma
aproximação padrão de calculadoras leves de push/fold — o suficiente para
apontar "essa mão deveria ter empurrado/foldado" com boa precisão, mas não
é um solver ICM/range-exato como GTO Wizard/ICMizer.
"""
from __future__ import annotations

import itertools
import json
import random
from functools import lru_cache
from pathlib import Path

RANKS = "23456789TJQKA"
RANK_VALUE = {r: i for i, r in enumerate(RANKS, start=2)}
SUITS = "shdc"

CACHE_PATH = Path(__file__).with_name("ranking_cache.json")


def parse_card(s: str) -> tuple[int, str]:
    s = s.strip()
    rank, suit = s[0].upper(), s[1].lower()
    return RANK_VALUE[rank], suit


def parse_hand(s: str) -> list[tuple[int, str]]:
    """'Kh 2h' / 'Kh2h' -> [(13,'h'), (2,'h')]"""
    s = s.replace(",", " ").strip()
    parts = s.split() if " " in s else [s[i:i + 2] for i in range(0, len(s), 2)]
    return [parse_card(p) for p in parts]


def full_deck() -> list[tuple[int, str]]:
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


def hand_rank5(cards: list[tuple[int, str]]) -> tuple:
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


def best_of_7(cards7: list[tuple[int, str]]) -> tuple:
    return max(hand_rank5(list(c)) for c in itertools.combinations(cards7, 5))


def _rng(seed: int | None) -> random.Random:
    return random.Random(seed) if seed is not None else random.Random()


def equity_hand_vs_hand(hero: list[tuple[int, str]], villain: list[tuple[int, str]],
                         trials: int = 1000, seed: int | None = None) -> float:
    """Equity do herói (fração 0..1, empate conta metade) contra uma mão
    específica do vilão, all-in preflop, via Monte Carlo do board."""
    rng = _rng(seed)
    dead = set(hero) | set(villain)
    deck = [c for c in full_deck() if c not in dead]
    wins = ties = 0
    for _ in range(trials):
        board = rng.sample(deck, 5)
        rh = best_of_7(hero + board)
        rv = best_of_7(villain + board)
        if rh > rv:
            wins += 1
        elif rh == rv:
            ties += 1
    return (wins + ties / 2) / trials


def equity_hand_vs_random(hero: list[tuple[int, str]], trials: int = 400,
                           seed: int | None = None) -> float:
    """Equity do herói contra UMA mão aleatória do vilão (não uma range),
    usada só para ranquear as 169 classes por força bruta."""
    rng = _rng(seed)
    deck = [c for c in full_deck() if c not in hero]
    wins = ties = 0
    for _ in range(trials):
        drawn = rng.sample(deck, 7)
        villain, board = drawn[:2], drawn[2:]
        rh = best_of_7(hero + board)
        rv = best_of_7(villain + board)
        if rh > rv:
            wins += 1
        elif rh == rv:
            ties += 1
    return (wins + ties / 2) / trials


def equity_hand_vs_range(hero: list[tuple[int, str]], villain_classes: list[str],
                          trials_per_class: int = 300, seed: int | None = None) -> float:
    """Equity do herói contra uma RANGE de classes de vilão (ex.: as top 20%
    calling hands). Pondera por nº de combos de cada classe (bloqueando
    combos que colidem com as cartas do herói)."""
    if not villain_classes:
        return 1.0
    rng = _rng(seed)
    total_w = 0.0
    acc = 0.0
    hero_set = set(hero)
    for cls in villain_classes:
        combos = class_combos(cls)
        combos = [c for c in combos if not (set(c) & hero_set)]
        if not combos:
            continue
        w = len(combos)
        # amostra algumas combinações da classe em vez de todas, se a
        # classe tiver muitas (offsuit = até 12) — mantém custo baixo.
        sample_combos = combos if len(combos) <= 4 else rng.sample(combos, 4)
        eq_sum = 0.0
        for vc in sample_combos:
            eq_sum += equity_hand_vs_hand(hero, list(vc), trials=trials_per_class, seed=seed)
        acc += (eq_sum / len(sample_combos)) * w
        total_w += w
    return acc / total_w if total_w else 1.0


# ---------------- Classes de mão (169) e ranges ----------------

def all_hand_classes() -> list[str]:
    """As 169 classes de mão inicial: 13 pares + 78 suited + 78 offsuit."""
    vals = list(reversed(RANKS))  # A, K, Q, ..., 2
    out = [r + r for r in vals]
    for i in range(len(vals)):
        for j in range(i + 1, len(vals)):
            out.append(vals[i] + vals[j] + "s")
            out.append(vals[i] + vals[j] + "o")
    return out


def class_combo_count(cls: str) -> int:
    if len(cls) == 2:
        return 6  # par
    return 4 if cls[2] == "s" else 12


@lru_cache(maxsize=None)
def class_combos(cls: str) -> tuple[tuple[tuple[int, str], tuple[int, str]], ...]:
    """Todas as combinações concretas de cartas de uma classe (ex. 'AKs')."""
    r1, r2 = RANK_VALUE[cls[0]], RANK_VALUE[cls[1]]
    if len(cls) == 2:  # par
        return tuple(
            ((r1, a), (r1, b))
            for a, b in itertools.combinations(SUITS, 2)
        )
    if cls[2] == "s":
        return tuple(((r1, s), (r2, s)) for s in SUITS)
    return tuple(
        ((r1, a), (r2, b))
        for a in SUITS for b in SUITS if a != b
    )


def class_representative(cls: str) -> list[tuple[int, str]]:
    """Uma combinação concreta representativa da classe, para os cálculos
    de equity vs range (ver limitação no docstring do módulo)."""
    return list(class_combos(cls)[0])


def class_of(cards: list[tuple[int, str]]) -> str:
    (r1, s1), (r2, s2) = cards
    hi, lo = max(r1, r2), min(r1, r2)
    hi_c = RANKS[hi - 2]
    lo_c = RANKS[lo - 2]
    if r1 == r2:
        return hi_c + hi_c
    return hi_c + lo_c + ("s" if s1 == s2 else "o")


def build_ranking(trials: int = 400, seed: int = 42) -> list[str]:
    """Ranqueia as 169 classes por equity vs mão aleatória (força bruta,
    calculado por este motor — não é tabela copiada). Resultado cacheado
    em disco (ranking_cache.json) porque leva alguns segundos."""
    if CACHE_PATH.exists():
        data = json.loads(CACHE_PATH.read_text())
        if data.get("trials") == trials and data.get("seed") == seed:
            return data["ranking"]

    scores = {}
    for cls in all_hand_classes():
        hero = class_representative(cls)
        scores[cls] = equity_hand_vs_random(hero, trials=trials, seed=seed)
    ranking = sorted(scores, key=lambda c: -scores[c])
    CACHE_PATH.write_text(json.dumps(
        {"trials": trials, "seed": seed, "ranking": ranking, "scores": scores},
        indent=0))
    return ranking


def range_top_pct(pct: float, ranking: list[str]) -> list[str]:
    """Expande um percentual (por combos, não por classes) numa lista de
    classes, ex.: range_top_pct(20, ranking) ~ top 20% das mãos por combo."""
    total = 1326
    target = pct / 100 * total
    chosen: list[str] = []
    cum = 0
    for cls in ranking:
        if cum >= target and chosen:
            break
        chosen.append(cls)
        cum += class_combo_count(cls)
    return chosen


def range_combo_pct(classes: list[str]) -> float:
    return sum(class_combo_count(c) for c in classes) / 1326 * 100


# ---------------- Matriz classe-vs-classe (para o solver) ----------------
#
# equity_hand_vs_range com Monte Carlo ao vivo é caro demais pra ser
# chamado O(169) vezes por iteração do solver Nash. Em vez disso,
# pré-computamos uma matriz 169x169 (representante-vs-representante,
# evitando cartas conflitantes) UMA VEZ, cacheada em disco — e o solver
# só faz somas ponderadas nela (rápido). A query final, com as cartas
# EXATAS da mão real do herói, ainda usa MC ao vivo em nash.ev_shove_bb
# (só roda uma vez por mão analisada, não 169x por iteração).

MATRIX_CACHE_PATH = Path(__file__).with_name("matrix_cache.json")


def _combo_avoiding(cls: str, blocked: set[tuple[int, str]]) -> list[tuple[int, str]] | None:
    for combo in class_combos(cls):
        if not (set(combo) & blocked):
            return list(combo)
    return None


def build_class_matrix(trials: int = 200, seed: int = 42) -> dict[str, float]:
    """Matriz de equity classe-vs-classe (chave 'A|B' -> equity de A contra
    B), cacheada em disco. ~14k pares únicos * `trials` deals de board."""
    if MATRIX_CACHE_PATH.exists():
        data = json.loads(MATRIX_CACHE_PATH.read_text())
        if data.get("trials") == trials and data.get("seed") == seed:
            return data["matrix"]

    classes = all_hand_classes()
    matrix: dict[str, float] = {}
    for i, a in enumerate(classes):
        ca = class_representative(a)
        for b in classes[i:]:
            if a == b:
                matrix[f"{a}|{b}"] = 0.5
                continue
            cb = _combo_avoiding(b, set(ca))
            if cb is None:
                matrix[f"{a}|{b}"] = matrix[f"{b}|{a}"] = 0.5
                continue
            e = equity_hand_vs_hand(ca, cb, trials=trials, seed=seed)
            matrix[f"{a}|{b}"] = e
            matrix[f"{b}|{a}"] = 1 - e
    MATRIX_CACHE_PATH.write_text(json.dumps({"trials": trials, "seed": seed, "matrix": matrix}))
    return matrix


def equity_class_vs_range(cls_a: str, range_classes: list[str], matrix: dict[str, float]) -> float:
    """Equity (aproximada, via matriz) da classe A contra uma range de
    classes B, ponderada por nº de combos de cada B."""
    if not range_classes:
        return 1.0
    total_w = 0.0
    acc = 0.0
    for b in range_classes:
        e = matrix.get(f"{cls_a}|{b}")
        if e is None:
            e = 0.5
        w = class_combo_count(b)
        acc += e * w
        total_w += w
    return acc / total_w if total_w else 1.0
