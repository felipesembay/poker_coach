"""Pot Odds Engine (Fase 2, Etapa 3 do Poker Decision Engine).

Calcula o custo de pagar uma aposta/raise/all-in e a equity mínima
necessária pra esse call ser +EV, a partir do estado da mão (pote antes
da ação, tamanho da aposta enfrentada, quanto o hero já colocou nessa
rodada, stack efetivo).

Não é recomendação de call — só a matemática do pote (ver seção 7.4 do
plano: equity estimada, required equity e EV ficam por conta do EV Engine,
Etapa 4, que ainda não foi implementado). Este módulo não calcula nem
assume equity nenhuma.

Regra de contribuição (seção 7.1 do plano): `hero_call_cost` é sempre
"quanto falta colocar", nunca o valor total da aposta — se o hero já
colocou fichas nessa rodada (ex.: deu o raise original e está enfrentando
um re-raise, ou postou blind), isso é descontado pra não contar 2x.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FACING_KINDS = ("bet", "raise", "allin")


class PotOddsInputError(ValueError):
    """Entrada inválida pro pot odds engine (valores negativos, call já pago, etc.)."""


@dataclass
class PotOddsResult:
    pot_before_bet: float
    villain_bet: float
    hero_already_in: float
    additional_money_in: float
    hero_call_cost: float
    pot_after_call: float
    required_equity: float
    pot_odds_ratio: str
    facing: str
    is_partial_call: bool
    hero_stack_after_call: float | None
    assumptions: list[str] = field(default_factory=list)


def _format_ratio(pot_before_call: float, call_cost: float) -> str:
    if call_cost <= 0:
        return "0:1"
    ratio = pot_before_call / call_cost
    if abs(ratio - round(ratio)) < 0.05:
        return f"{round(ratio)}:1"
    return f"{ratio:.1f}:1"


def calculate_pot_odds(
    pot_before_bet: float,
    bet_size: float,
    hero_already_in: float = 0.0,
    additional_money_in: float = 0.0,
    hero_stack: float | None = None,
    facing: str = "bet",
) -> PotOddsResult:
    """Calcula pot odds pro call do hero.

    - `pot_before_bet`: pote acumulado antes da ação que o hero está
      enfrentando (ruas anteriores + contribuições já feitas nessa rodada
      por todo mundo, exceto a ação do agressor).
    - `bet_size`: quanto o agressor colocou NESSA ação (o valor total que
      define o que precisa ser igualado — não o stack dele todo).
    - `hero_already_in`: quanto o hero já colocou NESSA MESMA rodada de
      apostas (blind, bet, raise anterior). Evita contar 2x.
    - `additional_money_in`: fichas extras de OUTROS jogadores que já
      pagaram/apostaram entre a ação original e a decisão do hero
      (multiway — pote fica maior antes do hero decidir).
    - `hero_stack`: stack restante do hero. Se menor que o custo do call,
      o call é parcial (all-in forçado) e os números refletem isso.
    - `facing`: "bet" | "raise" | "allin" — só rotula o contexto no
      resultado, não muda a matemática (a matemática é sempre a mesma:
      quanto falta pagar / pote final).
    """
    if facing not in FACING_KINDS:
        raise PotOddsInputError(f"facing inválido: {facing!r} (use {FACING_KINDS})")
    if pot_before_bet < 0:
        raise PotOddsInputError(f"pot_before_bet não pode ser negativo: {pot_before_bet}")
    if bet_size <= 0:
        raise PotOddsInputError(f"bet_size precisa ser positivo: {bet_size}")
    if hero_already_in < 0:
        raise PotOddsInputError(f"hero_already_in não pode ser negativo: {hero_already_in}")
    if additional_money_in < 0:
        raise PotOddsInputError(f"additional_money_in não pode ser negativo: {additional_money_in}")
    if hero_already_in > bet_size:
        raise PotOddsInputError(
            f"hero_already_in ({hero_already_in}) não pode ser maior que bet_size "
            f"({bet_size}) — hero não pode ter colocado mais do que precisa igualar"
        )
    if hero_stack is not None and hero_stack <= 0:
        raise PotOddsInputError(
            f"hero_stack precisa ser positivo pra existir uma decisão de call: {hero_stack}"
        )

    call_cost_full = bet_size - hero_already_in
    if call_cost_full <= 0:
        raise PotOddsInputError(
            "hero já igualou esse valor nessa rodada — não há call pendente "
            f"(hero_already_in={hero_already_in}, bet_size={bet_size})"
        )

    assumptions: list[str] = []
    is_partial_call = False
    call_cost = call_cost_full
    if hero_stack is not None and hero_stack < call_cost_full:
        call_cost = hero_stack
        is_partial_call = True
        assumptions.append(
            f"Stack do hero ({hero_stack}) é menor que o custo cheio do call "
            f"({call_cost_full}) — call parcial (all-in forçado por {call_cost}), "
            "não paga o valor total da aposta."
        )

    pot_before_call = pot_before_bet + bet_size + additional_money_in
    pot_after_call = pot_before_call + call_cost
    required_equity = call_cost / pot_after_call

    hero_stack_after_call = (hero_stack - call_cost) if hero_stack is not None else None

    assumptions.append(
        "Pot odds não é recomendação de call — compara só o custo contra o pote final. "
        "EV real depende da equity do hero, calculada separadamente (Equity Engine / EV Engine)."
    )
    if additional_money_in > 0:
        assumptions.append(
            f"Multiway: {additional_money_in} já entraram no pote de outros jogadores antes "
            "da decisão do hero, incluídos no pote final."
        )

    return PotOddsResult(
        pot_before_bet=pot_before_bet,
        villain_bet=bet_size,
        hero_already_in=hero_already_in,
        additional_money_in=additional_money_in,
        hero_call_cost=call_cost,
        pot_after_call=pot_after_call,
        required_equity=required_equity,
        pot_odds_ratio=_format_ratio(pot_before_call, call_cost),
        facing=facing,
        is_partial_call=is_partial_call,
        hero_stack_after_call=hero_stack_after_call,
        assumptions=assumptions,
    )
