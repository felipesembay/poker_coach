"""Context Classification + dispatcher (Fase 2, Etapa 5).

Decide QUAL motor usar num spot: o Nash push/fold isolado (existente,
`pushfold/nash.py`, preservado sem mudanças) ou o EV Engine contextual
novo (`ev_engine.py`, Etapa 4) — e expõe essa escolha de forma
transparente (`ContextClassification.context_type`/`recommended_model`),
como pedido na seção 9 do plano.

Regra: só usa o Nash push/fold isolado quando a decisão É de fato uma
decisão de abertura preflop sem ação anterior (o caso pra que ele foi
desenhado). Qualquer ação anterior (facing bet/raise/all-in), em qualquer
street, cai no EV Engine contextual — que sabe lidar com pote real, custo
de call e multiway. Isso implementa a "regra fundamental" do plano: não
substituir o motor existente, só decidir quando ele se aplica.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import ev_engine
from .equity_engine import EquityOpponent
from .ev_engine import ContextualEVResult
from .pushfold import equity as pf_equity
from .pushfold import nash as pf_nash

STREETS = ("preflop", "flop", "turn", "river")
FACING_KINDS = ("none", "bet", "raise", "allin")


class ContextInputError(ValueError):
    """Entrada inválida pro classificador/dispatcher de contexto."""


@dataclass
class ContextClassification:
    context_type: str
    recommended_model: str
    reasoning: list[str]


@dataclass
class NashDecision:
    """Resultado do motor Nash push/fold ISOLADO (sem ação anterior) —
    não confundir com o EV contextual de push do `ev_engine` (ver
    docstring de `ev_engine.py`, seção 8.5 do plano)."""
    recommendation: str  # "push" | "fold"
    ev_push_bb: float
    equity_vs_call_range: float
    call_pct: float
    effective_bb: float
    pot_bb: float


@dataclass
class DecisionAnalysis:
    context: ContextClassification
    nash: NashDecision | None
    contextual: ContextualEVResult | None


def classify_context(street: str, facing: str, num_players_in_hand: int) -> ContextClassification:
    """Classifica um spot num dos contextos da seção 9 do plano.

    `facing`: "none" (hero age primeiro / ninguém apostou ainda nessa
    rodada), "bet", "raise" ou "allin".
    `num_players_in_hand`: quantos jogadores (incluindo o hero) ainda
    seguem na mão nessa decisão — >2 = multiway.
    """
    if street not in STREETS:
        raise ContextInputError(f"street inválida: {street!r} (use {STREETS})")
    if facing not in FACING_KINDS:
        raise ContextInputError(f"facing inválido: {facing!r} (use {FACING_KINDS})")
    if num_players_in_hand < 2:
        raise ContextInputError(
            f"num_players_in_hand precisa ser >= 2 (hero + pelo menos 1 vilão): {num_players_in_hand}"
        )

    is_preflop = street == "preflop"
    is_multiway = num_players_in_hand > 2

    if facing == "none":
        if is_preflop:
            return ContextClassification(
                context_type="preflop_open",
                recommended_model="pushfold_nash",
                reasoning=[
                    "Preflop, ninguém apostou ainda nessa rodada — spot clássico de "
                    "abertura, exatamente o que o motor Nash push/fold isolado resolve.",
                ],
            )
        return ContextClassification(
            context_type="postflop_first_to_act",
            recommended_model="postflop_check_only",
            reasoning=[
                f"{street.capitalize()}, hero age primeiro e ninguém apostou ainda — "
                "única decisão incremental bem definida nesta etapa é Check "
                "(apostar/bet-sizing do hero não é modelado ainda).",
            ],
        )

    # facing bet/raise/allin — há ação anterior, motor isolado não se aplica.
    reasoning = [
        f"Há ação anterior ({facing}) que o motor Nash push/fold isolado não "
        "enxerga — ele só resolve a decisão de abrir o pote, não de responder "
        "a uma aposta. Isso cai no EV Engine contextual (pot odds + equity "
        "vs. range real dos vilões que seguem).",
    ]
    if is_multiway:
        reasoning.append(
            f"{num_players_in_hand} jogadores seguem na mão — equity precisa ser "
            "calculada contra múltiplos adversários (multiway), não heads-up."
        )
    context_type = ("_".join(filter(None, [
        street, "multiway" if is_multiway else None, "facing", facing,
    ])))
    return ContextClassification(
        context_type=context_type,
        recommended_model="contextual_ev",
        reasoning=reasoning,
    )


def analyze_decision(
    *,
    street: str,
    facing: str,
    num_players_in_hand: int,
    hero_cards: list[str],
    board: list[str] | None = None,
    # -- modelo pushfold_nash (preflop_open) --
    effective_bb: float | None = None,
    pot_bb: float | None = None,
    # -- modelo contextual_ev / postflop_check_only --
    opponents: list[EquityOpponent] | None = None,
    pot_before_bet: float = 0.0,
    bet_size: float = 0.0,
    hero_already_in: float = 0.0,
    additional_money_in: float = 0.0,
    hero_stack: float | None = None,
    villain_stack: float | None = None,
    equity_simulation_method: str = "auto",
    equity_iterations: int | None = None,
    equity_seed: int | None = None,
) -> DecisionAnalysis:
    """Classifica o contexto e chama o motor certo, retornando os dois
    campos (`nash`/`contextual`) sempre com um deles None — nunca mistura
    os dois modelos na mesma resposta (seção 11.3 do plano: não misturar
    EV Nash com EV contextual)."""
    context = classify_context(street, facing, num_players_in_hand)
    board = board or []

    if context.recommended_model == "pushfold_nash":
        if effective_bb is None or pot_bb is None:
            raise ContextInputError(
                "contexto classificado como 'pushfold_nash' precisa de effective_bb e pot_bb"
            )
        if len(hero_cards) != 2:
            raise ContextInputError(f"hero_cards precisa ter 2 cartas, recebeu {hero_cards!r}")
        try:
            hero_tuples = [pf_equity.parse_card(c) for c in hero_cards]
        except (KeyError, IndexError) as exc:
            raise ContextInputError(f"carta inválida em hero_cards ({hero_cards!r}): {exc}") from exc

        solved = pf_nash.solve(effective_bb, pot_bb)
        call_pct = solved.call_pct / 100
        ev_bb, equity_vs_range = pf_nash.ev_shove_bb(
            hero_tuples, solved.call_classes, effective_bb, pot_bb, call_pct
        )
        # Recomendação vem do SINAL do EV via Monte Carlo ao vivo com as
        # cartas exatas do herói — mesma convenção de `pushfold/analyze.py`
        # (`analyze_hand_row`, precise=True). NÃO usar `should_shove()`
        # (baseado na classe/matriz de equilíbrio): ela e o EV ao vivo podem
        # discordar em spots marginais (classe está na range de equilíbrio,
        # mas a combinação exata do herói, com bloqueio de cartas real, tem
        # EV negativo) — confirmado com uma mão real durante o teste desta
        # integração.
        nash = NashDecision(
            recommendation="push" if ev_bb > 0 else "fold",
            ev_push_bb=ev_bb,
            equity_vs_call_range=equity_vs_range,
            call_pct=call_pct,
            effective_bb=effective_bb,
            pot_bb=pot_bb,
        )
        return DecisionAnalysis(context=context, nash=nash, contextual=None)

    facing_bet = facing != "none"
    contextual = ev_engine.evaluate_decision(
        facing_bet=facing_bet,
        street=street,
        hero_cards=hero_cards,
        board=board,
        opponents=opponents,
        pot_before_bet=pot_before_bet,
        bet_size=bet_size,
        hero_already_in=hero_already_in,
        additional_money_in=additional_money_in,
        hero_stack=hero_stack,
        villain_stack=villain_stack,
        facing=facing if facing_bet else "bet",
        equity_simulation_method=equity_simulation_method,
        equity_iterations=equity_iterations,
        equity_seed=equity_seed,
    )
    return DecisionAnalysis(context=context, nash=None, contextual=contextual)
