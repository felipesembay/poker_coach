"""Motor de equity pós-flop (Fase 1 do Poker Decision Engine).

Reaproveita o avaliador de mão de `handeval.py` (extraído de
`pushfold/equity.py`, sem duplicação) e os utilitários de range/classe de
`pushfold/equity.py` (all_hand_classes/class_combos/class_of). Não
substitui o motor push/fold — é uma camada nova, usada por cima dele.

Suporta: preflop, flop, turn, river; hero vs 1 mão exata; hero vs 1 range;
hero vs N adversários (multiway) via Monte Carlo.

Premissas documentadas (não escondidas):
- Ranges são listas explícitas de classes de 169 mãos (ex. "AKs", "77"),
  no mesmo formato usado pelo motor push/fold. Não há ranges nomeadas
  pré-definidas (ex. "BB_DEFAULT_RANGE") — quem chama precisa fornecer a
  lista de classes, ou omitir o range para "qualquer duas cartas".
- Multiway é resolvido por simulação Monte Carlo conjunta (um vilão por
  vez, sorteado do próprio range, cartas sem colisão) — nunca reaproveita
  equity heads-up como se fosse equity multiway.
- "Outs" só são calculados no caso heads-up (exatamente 1 adversário).
  Contra um range, um out é conservador: só conta se vence TODAS as
  combinações restantes do range do vilão, não a média ponderada.
- `river_improvement_probability` no flop reusa o conjunto de outs
  calculado a partir do board de 3 cartas (não recalcula outs após um
  turn "brick") — é uma aproximação padrão de calculadoras leves,
  registrada em `assumptions`, não um resultado exato do runout completo.
"""
from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field

from .handeval import RANKS, Card, best_of_n, full_deck, parse_card
from .pushfold.equity import all_hand_classes, class_combos

STREET_BOARD_SIZE = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
_ALL_CLASSES = set(all_hand_classes())

DEFAULT_MC_ITERATIONS = 20_000
MIN_MC_ITERATIONS = 1_000
MAX_MC_ITERATIONS = 200_000
EXACT_MAX_EVALUATIONS = 150_000


class EquityInputError(ValueError):
    """Entrada inválida pro equity engine (cartas/board/range malformados)."""


@dataclass
class EquityOpponent:
    player_id: str
    cards: list[str] | None = None
    range_classes: list[str] | None = None


@dataclass
class EquityResult:
    hero_equity: float
    win_probability: float
    tie_probability: float
    loss_probability: float
    outs: list[str]
    turn_improvement_probability: float | None
    river_improvement_probability: float | None
    simulation_method: str  # "exact" | "monte_carlo"
    iterations: int
    confidence_interval: tuple[float, float] | None
    num_opponents: int
    assumptions: list[str] = field(default_factory=list)


# ---------------- validação e parsing ----------------

def _parse_cards(raw: list[str], label: str) -> list[Card]:
    try:
        return [parse_card(c) for c in raw]
    except (KeyError, IndexError) as exc:
        raise EquityInputError(f"carta inválida em {label} ({raw}): {exc}") from exc


def _validate_range(cls_list: list[str], label: str) -> None:
    bad = [c for c in cls_list if c not in _ALL_CLASSES]
    if bad:
        raise EquityInputError(f"classes de mão inválidas em {label}: {bad}")


@dataclass
class _ParsedOpponent:
    player_id: str
    cards: list[Card] | None
    range_classes: list[str] | None


def _validate_and_parse(
    street: str,
    hero_cards: list[str],
    board: list[str],
    opponents: list[EquityOpponent],
    dead_cards: list[str] | None,
) -> tuple[list[Card], list[Card], list[Card], list[_ParsedOpponent]]:
    if street not in STREET_BOARD_SIZE:
        raise EquityInputError(f"street inválida: {street!r} (use {list(STREET_BOARD_SIZE)})")
    if len(hero_cards) != 2:
        raise EquityInputError(f"hero_cards precisa ter 2 cartas, recebeu {hero_cards!r}")
    hero = _parse_cards(hero_cards, "hero_cards")

    expected_board = STREET_BOARD_SIZE[street]
    if len(board) != expected_board:
        raise EquityInputError(
            f"board incompleto/incompatível pra street={street!r}: "
            f"esperado {expected_board} cartas, recebeu {len(board)} ({board!r})"
        )
    board_cards = _parse_cards(board, "board")

    dead = _parse_cards(dead_cards or [], "dead_cards")

    if not opponents:
        raise EquityInputError("precisa de pelo menos 1 adversário em 'opponents'")

    parsed_opponents: list[_ParsedOpponent] = []
    known: dict[Card, str] = {}

    def _claim(cards: list[Card], label: str) -> None:
        for c in cards:
            if c in known:
                raise EquityInputError(f"carta duplicada: {c} aparece em '{known[c]}' e '{label}'")
            known[c] = label

    _claim(hero, "hero_cards")
    _claim(board_cards, "board")
    _claim(dead, "dead_cards")

    for opp in opponents:
        if opp.cards and opp.range_classes:
            raise EquityInputError(
                f"opponent {opp.player_id!r}: informe 'cards' OU 'range_classes', não os dois"
            )
        opp_cards: list[Card] | None = None
        if opp.cards:
            if len(opp.cards) != 2:
                raise EquityInputError(f"opponent {opp.player_id!r}: cards precisa ter 2 cartas")
            opp_cards = _parse_cards(opp.cards, f"opponent {opp.player_id}")
            _claim(opp_cards, f"opponent {opp.player_id}")
        elif opp.range_classes:
            _validate_range(opp.range_classes, f"opponent {opp.player_id}")
        parsed_opponents.append(
            _ParsedOpponent(opp.player_id, opp_cards, opp.range_classes)
        )

    return hero, board_cards, dead, parsed_opponents


# ---------------- sorteio de mão de adversário (Monte Carlo) ----------------

def _weighted_class_choice(rng: random.Random, classes: list[str]) -> str:
    weights = [len(class_combos(c)) for c in classes]
    return rng.choices(classes, weights=weights, k=1)[0]


def _draw_opponent_hand(
    rng: random.Random, opp: _ParsedOpponent, dead: set[Card], deck: list[Card]
) -> list[Card] | None:
    """Sorteia 2 cartas pro adversário nesse trial, evitando `dead`.
    Retorna None se não sobrou nenhuma combinação viável (ranges muito
    restritas colidindo com o board/hero/outros vilões)."""
    if opp.cards:
        return opp.cards if not (set(opp.cards) & dead) else None

    if opp.range_classes:
        remaining_classes = list(opp.range_classes)
        rng.shuffle(remaining_classes)
        for cls in remaining_classes:
            combos = [c for c in class_combos(cls) if not (set(c) & dead)]
            if combos:
                return list(rng.choice(combos))
        return None

    # sem cards nem range: qualquer duas cartas do baralho restante
    avail = [c for c in deck if c not in dead]
    if len(avail) < 2:
        return None
    return rng.sample(avail, 2)


# ---------------- avaliação e agregação de um "deal" completo ----------------

def _score_deal(hero: list[Card], board: list[Card], opp_hands: list[list[Card]]) -> float:
    """Retorna a fração de equity do hero nesse deal (1.0 vitória solo,
    1/k em empate de k jogadores, 0.0 derrota)."""
    hero_rank = best_of_n(hero + board)
    opp_ranks = [best_of_n(h + board) for h in opp_hands]
    best = max([hero_rank, *opp_ranks])
    if hero_rank < best:
        return 0.0
    tied = 1 + sum(1 for r in opp_ranks if r == best)
    return 1.0 / tied


def _outcome_kind(hero: list[Card], board: list[Card], opp_hands: list[list[Card]]) -> str:
    hero_rank = best_of_n(hero + board)
    opp_ranks = [best_of_n(h + board) for h in opp_hands]
    best = max([hero_rank, *opp_ranks])
    if hero_rank < best:
        return "loss"
    if any(r == best for r in opp_ranks):
        return "tie"
    return "win"


# ---------------- caminho exato (heads-up, poucas incógnitas) ----------------

def _opponent_combo_space(opp: _ParsedOpponent, dead: set[Card]) -> list[list[Card]] | None:
    """None = adversário é 'qualquer duas cartas' (não enumerável de forma
    compacta o suficiente pra caminho exato)."""
    if opp.cards:
        return [opp.cards]
    if opp.range_classes:
        out = []
        for cls in opp.range_classes:
            out.extend(list(c) for c in class_combos(cls) if not (set(c) & dead))
        return out
    return None


def _try_exact(
    hero: list[Card],
    board: list[Card],
    dead: set[Card],
    deck: list[Card],
    need: int,
    opponents: list[_ParsedOpponent],
) -> tuple[str, int] | None:
    """Tenta montar o espaço de enumeração exata. Retorna None se algum
    adversário é 'qualquer duas cartas' (espaço grande demais/mal-definido
    pra exato) ou se o total de avaliações passa do limite — nesse caso o
    chamador cai pro Monte Carlo."""
    combo_spaces = [_opponent_combo_space(o, dead) for o in opponents]
    if any(cs is None for cs in combo_spaces):
        return None

    board_combos = list(itertools.combinations(deck, need)) if need else [()]
    total = len(board_combos)
    for cs in combo_spaces:
        total *= max(len(cs), 1)
    if total == 0:
        return None
    if total > EXACT_MAX_EVALUATIONS:
        return None
    return "ok", total  # sinaliza viável; enumeração real feita pelo chamador


def _run_exact(
    hero: list[Card],
    board: list[Card],
    dead: set[Card],
    deck: list[Card],
    need: int,
    opponents: list[_ParsedOpponent],
) -> tuple[dict[str, int], float, int]:
    combo_spaces = [_opponent_combo_space(o, dead) for o in opponents]
    counts = {"win": 0, "tie": 0, "loss": 0}
    equity_sum = 0.0
    n = 0
    board_combos = itertools.combinations(deck, need) if need else [()]
    for missing in board_combos:
        full_board = board + list(missing)
        missing_set = set(missing)
        # produto cartesiano dos adversários, filtrando colisão entre eles.
        # `dead` (hero/board/dead_cards/vilões fixos) já foi aplicado na
        # construção de combo_spaces — aqui só falta checar colisão com o
        # board sorteado nessa iteração (`missing`), que não é conhecido
        # de antemão pra um vilão de range (ele pode segurar qualquer carta
        # que por acaso caiu no board de uma combinação diferente).
        for combo in itertools.product(*combo_spaces):
            flat = [c for hand in combo for c in hand]
            if len(set(flat)) != len(flat):
                continue
            if set(flat) & missing_set:
                continue
            opp_hands = [list(h) for h in combo]
            counts[_outcome_kind(hero, full_board, opp_hands)] += 1
            equity_sum += _score_deal(hero, full_board, opp_hands)
            n += 1
    if n == 0:
        raise EquityInputError(
            "nenhuma combinação viável de board/adversários — range ou dead cards "
            "deixaram o espaço vazio"
        )
    return counts, equity_sum / n, n


def _run_monte_carlo(
    hero: list[Card],
    board: list[Card],
    dead: set[Card],
    deck: list[Card],
    need: int,
    opponents: list[_ParsedOpponent],
    iterations: int,
    seed: int | None,
) -> tuple[dict[str, int], float, int]:
    rng = random.Random(seed) if seed is not None else random.Random()
    counts = {"win": 0, "tie": 0, "loss": 0}
    equity_sum = 0.0
    n = 0
    attempts_cap = iterations * 5  # evita loop infinito se o espaço for quase impossível
    attempts = 0
    while n < iterations and attempts < attempts_cap:
        attempts += 1
        trial_dead = set(dead)
        opp_hands: list[list[Card]] = []
        ok = True
        for opp in opponents:
            hand = _draw_opponent_hand(rng, opp, trial_dead, deck)
            if hand is None:
                ok = False
                break
            opp_hands.append(hand)
            trial_dead |= set(hand)
        if not ok:
            continue
        avail = [c for c in deck if c not in trial_dead]
        if len(avail) < need:
            continue
        missing = rng.sample(avail, need) if need else []
        full_board = board + missing
        counts[_outcome_kind(hero, full_board, opp_hands)] += 1
        equity_sum += _score_deal(hero, full_board, opp_hands)
        n += 1
    if n == 0:
        raise EquityInputError(
            "não foi possível simular nenhum deal válido — range ou dead cards "
            "deixaram o espaço vazio"
        )
    return counts, equity_sum / n, n


# ---------------- outs (heads-up apenas) ----------------

def _compute_outs(
    hero: list[Card],
    board: list[Card],
    dead: set[Card],
    deck: list[Card],
    opp: _ParsedOpponent,
) -> list[Card]:
    """Cartas que, se forem a PRÓXIMA carta comunitária, fazem o hero
    passar a vencer o vilão (mão exata) ou TODAS as combos restantes do
    range do vilão (definição conservadora, documentada no docstring do
    módulo)."""
    # `_opponent_combo_space` já filtra combos de range contra `dead`; pra
    # vilão de mão fixa, os combos SÃO parte de `dead` (foram reivindicados
    # em `_validate_and_parse`), então não re-filtramos aqui — faria toda
    # combinação colidir consigo mesma.
    villain_combos = _opponent_combo_space(opp, dead)
    if not villain_combos:
        return []  # vilão "qualquer duas cartas": outs não são bem definidos

    hero_rank_now = best_of_n(hero + board)
    already_ahead = all(hero_rank_now > best_of_n(list(vh) + board) for vh in villain_combos)
    if already_ahead:
        # hero já vence toda combinação atual do vilão nesse board — não há
        # "melhora" a buscar (outs tradicionalmente é sobre virar o jogo).
        return []

    outs: list[Card] = []
    for card in deck:
        if card in dead:
            continue
        trial_board = board + [card]
        hero_rank = best_of_n(hero + trial_board)
        beats_all = True
        any_valid = False
        for vh in villain_combos:
            if set(vh) & {card}:
                continue
            any_valid = True
            if best_of_n(list(vh) + trial_board) >= hero_rank:
                beats_all = False
                break
        if any_valid and beats_all:
            outs.append(card)
    return outs


def _card_str(c: Card) -> str:
    rank, suit = c
    return f"{RANKS[rank - 2]}{suit}"


# ---------------- entrada pública ----------------

def calculate_equity(
    street: str,
    hero_cards: list[str],
    board: list[str],
    opponents: list[EquityOpponent],
    dead_cards: list[str] | None = None,
    simulation_method: str = "auto",
    iterations: int | None = None,
    seed: int | None = None,
) -> EquityResult:
    """Calcula equity pós-flop (ou preflop, via Monte Carlo) do hero contra
    1+ adversários. Ver docstring do módulo pras premissas assumidas."""
    if simulation_method not in ("auto", "exact", "monte_carlo"):
        raise EquityInputError(
            f"simulation_method inválido: {simulation_method!r} "
            "(use 'auto', 'exact' ou 'monte_carlo')"
        )

    hero, board_cards, dead, opponents_parsed = _validate_and_parse(
        street, hero_cards, board, opponents, dead_cards
    )
    known = set(hero) | set(board_cards) | set(dead)
    for opp in opponents_parsed:
        if opp.cards:
            known |= set(opp.cards)
    deck = [c for c in full_deck() if c not in known]
    need = 5 - len(board_cards)

    assumptions = [
        "Ranges são listas explícitas de classes (169 tipos), sem ranges nomeadas pré-definidas.",
    ]
    if len(opponents_parsed) > 1:
        assumptions.append(
            "Multiway: cada adversário é sorteado independentemente do próprio range, "
            "sem correlação entre ranges (nenhum adversário 'sabe' a mão do outro)."
        )

    requested_iterations = iterations or DEFAULT_MC_ITERATIONS
    requested_iterations = max(MIN_MC_ITERATIONS, min(MAX_MC_ITERATIONS, requested_iterations))

    use_exact = False
    if simulation_method == "exact":
        use_exact = True
    elif simulation_method == "auto":
        feasible = _try_exact(hero, board_cards, known, deck, need, opponents_parsed)
        use_exact = feasible is not None

    if use_exact:
        feasible = _try_exact(hero, board_cards, known, deck, need, opponents_parsed)
        if feasible is None:
            if simulation_method == "exact":
                raise EquityInputError(
                    "cálculo exato pedido, mas algum adversário é 'qualquer duas cartas' "
                    "ou o espaço de enumeração é grande demais — use range_classes explícito "
                    "ou simulation_method='monte_carlo'"
                )
            use_exact = False

    if use_exact:
        counts, hero_equity, n = _run_exact(hero, board_cards, known, deck, need, opponents_parsed)
        method = "exact"
        confidence_interval = None
    else:
        counts, hero_equity, n = _run_monte_carlo(
            hero, board_cards, known, deck, need, opponents_parsed, requested_iterations, seed
        )
        method = "monte_carlo"
        se = math.sqrt(max(hero_equity * (1 - hero_equity), 0.0) / n)
        confidence_interval = (
            max(0.0, hero_equity - 1.96 * se),
            min(1.0, hero_equity + 1.96 * se),
        )
        assumptions.append(
            f"Monte Carlo com {n} iterações válidas — resultado é uma estimativa, "
            "não um cálculo exato (ver confidence_interval)."
        )

    outs: list[Card] = []
    turn_improve: float | None = None
    river_improve: float | None = None
    if len(opponents_parsed) == 1 and street in ("flop", "turn"):
        outs = _compute_outs(hero, board_cards, known, deck, opponents_parsed[0])
        remaining = len(deck)
        if street == "flop":
            turn_improve = len(outs) / remaining if remaining else 0.0
            if remaining >= 2:
                miss = 1 - (len(outs) / remaining)
                miss_both = miss * ((remaining - len(outs) - 1) / (remaining - 1)) if remaining > 1 else miss
                river_improve = 1 - miss_both
            assumptions.append(
                "river_improvement_probability no flop reusa o conjunto de outs calculado "
                "a partir do board de 3 cartas, sem recalcular outs após o turn (aproximação "
                "padrão, não um cálculo exato do runout completo)."
            )
        elif street == "turn":
            river_improve = len(outs) / remaining if remaining else 0.0
    elif len(opponents_parsed) > 1:
        assumptions.append(
            "outs e turn/river_improvement_probability não são calculados em situações "
            "multiway (mais de 1 adversário) — conceito de 'out' fica mal definido sem "
            "um único vilão de referência."
        )

    total = counts["win"] + counts["tie"] + counts["loss"]
    return EquityResult(
        hero_equity=hero_equity,
        win_probability=counts["win"] / total,
        tie_probability=counts["tie"] / total,
        loss_probability=counts["loss"] / total,
        outs=[_card_str(c) for c in outs],
        turn_improvement_probability=turn_improve,
        river_improvement_probability=river_improve,
        simulation_method=method,
        iterations=n,
        confidence_interval=confidence_interval,
        num_opponents=len(opponents_parsed),
        assumptions=assumptions,
    )
