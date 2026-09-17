"""EV Engine contextual (Fase 2, Etapa 4 do Poker Decision Engine).

Liga o Equity Engine (`equity_engine.py`) e o Pot Odds Engine
(`pot_odds.py`) pra calcular EV de Fold/Call/Push a partir do estado real
da mão — pote, aposta enfrentada, quantos jogadores seguem na mão — em vez
de só olhar as cartas do hero como o motor Nash push/fold isolado faz.

NÃO substitui `pushfold/nash.py`. É uma camada nova, usada quando já
existe ação anterior (facing bet/raise/all-in) — ver `context.py`
(Etapa 5, classificação de contexto) pra decidir qual motor usar em cada
spot.

Modelos e limitações (documentados, não escondidos — ver seção 14 do
plano, "não inventar dados"):

- `EV(Call) = equity × pote_final − custo_do_call` (fórmula simplificada,
  seção 8.3 do plano). Não modela ações futuras (não sabe se o hero vai
  apostar/pagar mais nas próximas streets) — é o EV incremental DESSA
  decisão, não da mão inteira.
- `EV(Fold) = 0` por convenção (seção 8.4): é o ponto de referência —
  fichas já investidas são custo afundado, não entram nessa conta.
- `EV(Push)` só é calculado heads-up (1 adversário) e SÓ quando o stack
  do vilão é fornecido explicitamente. Sem esse dado, push fica marcado
  como não aplicável — o motor não inventa um stack de vilão.
  A fórmula reaproveita a mesma matemática de `pushfold/nash.py`
  (`equity × (pote_morto + 2×efetivo) − efetivo`), mas SEM o termo de
  fold equity do vilão (não temos como estimar a frequência de fold sem
  dados de exploração real) — ou seja, assume P(call do vilão) = 100%.
  Isso normalmente SUBESTIMA o EV real do push (fold ganha o pote na
  hora), e é explicitamente diferente do EV do Nash Push/Fold isolado
  (que resolve o jogo completo, com fold equity, mas ignora a ação
  anterior real da mão).
- Multiway (>1 adversário) não modela push nesta etapa — a matemática de
  quem paga o quê num all-in com múltiplos stacks diferentes vira side
  pots, que não é resolvido aqui ainda.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .equity_engine import EquityOpponent, EquityResult, calculate_equity
from .pot_odds import PotOddsResult, calculate_pot_odds

MODEL_NAME = "contextual_ev_v1"


class EVInputError(ValueError):
    """Entrada inválida pro EV engine contextual."""


@dataclass
class DecisionEV:
    action: str  # "fold" | "call" | "push" | "check"
    applicable: bool
    ev: float | None
    note: str


@dataclass
class ContextualEVResult:
    decisions: list[DecisionEV]
    equity: EquityResult | None
    pot_odds: PotOddsResult | None
    model: str
    assumptions: list[str] = field(default_factory=list)

    def best(self) -> DecisionEV | None:
        """Ação aplicável de maior EV. Retorna None se nada for aplicável
        (não deveria acontecer, mas não assume otimisticamente)."""
        applicable = [d for d in self.decisions if d.applicable and d.ev is not None]
        if not applicable:
            return None
        return max(applicable, key=lambda d: d.ev)


def evaluate_decision(
    *,
    facing_bet: bool,
    street: str,
    hero_cards: list[str],
    board: list[str],
    opponents: list[EquityOpponent] | None = None,
    pot_before_bet: float = 0.0,
    bet_size: float = 0.0,
    hero_already_in: float = 0.0,
    additional_money_in: float = 0.0,
    hero_stack: float | None = None,
    villain_stack: float | None = None,
    facing: str = "bet",
    equity_simulation_method: str = "auto",
    equity_iterations: int | None = None,
    equity_seed: int | None = None,
) -> ContextualEVResult:
    """Calcula EV contextual de Fold/Call/Push (e Check, se não há aposta
    pra enfrentar) pro estado de mão descrito.

    `facing_bet=False` -> só Check é avaliado (EV incremental 0; ver
    docstring do módulo — decisão de apostar/check-raise não é coberta
    nesta etapa).

    `facing_bet=True` -> exige `opponents` (range/mão do(s) vilão(ões),
    mesmo formato do Equity Engine) pra estimar equity. Fold e Call são
    sempre avaliados; Push só quando heads-up e `villain_stack` é dado.
    """
    if not facing_bet:
        decisions = [
            DecisionEV(
                "check", True, 0.0,
                "Sem aposta pra pagar — EV incremental do check é 0 "
                "(streets futuras não são modeladas nesta etapa)."
            ),
            DecisionEV("fold", False, None, "Não há aposta pra foldar."),
            DecisionEV("call", False, None, "Não há aposta pra pagar."),
            DecisionEV(
                "push", False, None,
                "Sem aposta enfrentada — apostar/dar all-in aqui seria uma "
                "aposta nova do hero, não coberta nesta etapa (só respostas "
                "a aposta do vilão)."
            ),
        ]
        return ContextualEVResult(
            decisions=decisions,
            equity=None,
            pot_odds=None,
            model=MODEL_NAME,
            assumptions=[
                "Nenhuma aposta enfrentada — apenas Check é uma decisão "
                "incremental válida nesta etapa."
            ],
        )

    if not opponents:
        raise EVInputError(
            "opponents é obrigatório quando facing_bet=True — precisa de range/mão "
            "do(s) vilão(ões) pra estimar equity"
        )

    pot_odds = calculate_pot_odds(
        pot_before_bet=pot_before_bet,
        bet_size=bet_size,
        hero_already_in=hero_already_in,
        additional_money_in=additional_money_in,
        hero_stack=hero_stack,
        facing=facing,
    )
    equity = calculate_equity(
        street=street,
        hero_cards=hero_cards,
        board=board,
        opponents=opponents,
        simulation_method=equity_simulation_method,
        iterations=equity_iterations,
        seed=equity_seed,
    )

    ev_call = equity.hero_equity * pot_odds.pot_after_call - pot_odds.hero_call_cost
    decisions = [
        DecisionEV(
            "fold", True, 0.0,
            "EV de referência — fichas já investidas são custo afundado, não "
            "entram nessa conta (ver seção 8.4 do plano)."
        ),
        DecisionEV(
            "call", True, ev_call,
            f"EV(Call) = equity ({equity.hero_equity:.1%}) × pote final "
            f"({pot_odds.pot_after_call:g}) − custo do call ({pot_odds.hero_call_cost:g}). "
            "Modelo simplificado (seção 8.3): não modela ações futuras."
        ),
    ]

    call_cost_full = bet_size - hero_already_in
    can_push_more_than_call = hero_stack is not None and hero_stack > call_cost_full
    is_heads_up = len(opponents) == 1
    if not can_push_more_than_call:
        decisions.append(
            DecisionEV(
                "push", False, None,
                "Stack do hero não dá pra empurrar mais do que o call (ou stack não "
                "foi informado) — push seria idêntico ao call, não é uma ação distinta."
            )
        )
    elif not is_heads_up:
        decisions.append(
            DecisionEV(
                "push", False, None,
                "Multiway (mais de 1 adversário): EV de all-in com múltiplos stacks "
                "diferentes envolve side pots, não resolvido nesta etapa."
            )
        )
    elif villain_stack is None:
        decisions.append(
            DecisionEV(
                "push", False, None,
                "Stack do vilão não foi informado — motor não estima push sem esse dado "
                "(evita inventar um número)."
            )
        )
    else:
        eff = min(hero_stack, villain_stack)
        dead_pot = pot_before_bet + bet_size + additional_money_in
        ev_push_if_called = equity.hero_equity * (dead_pot + 2 * eff) - eff
        decisions.append(
            DecisionEV(
                "push", True, ev_push_if_called,
                "Assume que o vilão SEMPRE paga (sem modelo de fold equity) — EV real "
                "tende a ser maior. Não é o mesmo EV do Nash Push/Fold isolado."
            )
        )

    decisions.append(
        DecisionEV("check", False, None, "Há aposta pra responder — check não é válido aqui.")
    )

    assumptions = [
        *equity.assumptions,
        *pot_odds.assumptions,
    ]
    return ContextualEVResult(
        decisions=decisions,
        equity=equity,
        pot_odds=pot_odds,
        model=MODEL_NAME,
        assumptions=assumptions,
    )
