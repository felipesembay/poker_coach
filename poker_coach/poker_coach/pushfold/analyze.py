"""Aplica o solver de Nash às mãos reais do herói já importadas no banco,
para os spots de "abertura" (unopened): decidir se hero deveria ter dado
push ou fold, e quanto EV (em BB) foi ganho/perdido na decisão real.

Escopo (documentado, não escondido):
- só spots ONDE HERO É O PRIMEIRO A AGIR VOLUNTARIAMENTE no pote (ninguém
  deu raise/bet/allin/call antes) — os mesmos spots que
  stats.shortstack_fold_report já isola como "unopened".
- vilão modelado = a BB (ver limitação em pushfold/nash.py).
- hero_position == 'BB' é ignorado (BB não "abre", fecha a ação — spot
  diferente, fica pro roadmap "call ou fold vs shove").
- chip EV, não ICM — bolha/mesa final tendem a distorcer a decisão certa
  pra baixo (ICM real seria mais tight que isto); o motor de ICM entra
  numa fase futura.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

from ..models import Hand, Seat
from . import equity as eq
from . import nash

DEFAULT_MAX_BB = 25.0


@dataclass
class LeakRow:
    site: str
    hand_id: str
    tournament_id: str
    position: str
    hero_cards: str
    effective_bb: float
    pot_bb: float
    hero_decision: str    # "push" | "fold"
    nash_decision: str    # "push" | "fold"
    ev_push_bb: float      # EV do push com as cartas exatas, contra a call range de equilíbrio
    ev_lost_bb: float       # 0 se a decisão real bateu com o Nash
    ts: str | None = None   # timestamp da mão — pra agrupar por período (Evolução)


@lru_cache(maxsize=1)
def _ranking() -> list[str]:
    return eq.build_ranking()


@lru_cache(maxsize=1)
def _matrix() -> dict[str, float]:
    return eq.build_class_matrix()


@lru_cache(maxsize=512)
def _cached_solve(effective_bb_rounded: float, pot_bb_rounded: float) -> nash.NashResult:
    return nash.solve(effective_bb_rounded, pot_bb_rounded, _ranking(), _matrix())


def _bb_seat(seats: list[Seat], button_seat: int) -> Seat | None:
    stub = Hand(site="", hand_id="", tournament_id="", timestamp=None, level=None,
                sb=0, bb=0, ante=0, buyin=None, currency=None, table_name=None,
                max_players=None, button_seat=button_seat, seats=seats)
    return stub.seat_at_position("BB")


@dataclass
class FacingShoveRow:
    """Espelho de `LeakRow`, só que pro lado do CALLER: um vilão qualquer
    deu all-in (ninguém tinha entrado antes) e o herói decide pagar ou
    foldar — o cenário oposto de "abertura" (ver limitações no docstring
    de `analyze_facing_shove_hand_row`)."""
    site: str
    hand_id: str
    tournament_id: str
    position: str          # posição do herói (quem decide call/fold)
    shover_position: str    # posição de quem deu o all-in
    hero_cards: str
    effective_bb: float
    pot_bb: float           # dinheiro morto (blinds/antes) antes do all-in
    hero_decision: str      # "call" | "fold"
    nash_decision: str      # "call" | "fold"
    ev_call_bb: float        # EV de pagar (BB), relativo a foldar = 0
    ev_lost_bb: float         # 0 se a decisão real bateu com o Nash
    ts: str | None = None


def analyze_facing_shove_hand_row(conn: sqlite3.Connection, site: str, hand_id: str,
                                   max_bb: float = DEFAULT_MAX_BB,
                                   precise: bool = False,
                                   trials_final: int = 400) -> FacingShoveRow | None:
    """Mesma ideia de `analyze_hand_row`, só que pro lado de quem PAGA
    um all-in, não de quem abre.

    Escopo (documentado, não escondido):
    - só o all-in de UM vilão só, com o pote fechado até ali (ninguém
      tinha dado raise/bet/call antes do shove) — mesma simplificação
      heads-up do resto do motor, agora do ponto de vista do caller.
    - entre o shove e a vez do herói só pode haver folds — se um
      terceiro jogador pagar ou re-levantar antes do herói agir, o spot
      vira multiway/squeeze e sai do escopo (fora daqui).
    - herói precisa responder fold ou call; se ele mesmo re-shove
      (all-in por cima), o spot não é julgado (não é mais um call puro).
    - a range de shove assumida pro vilão é a de EQUILÍBRIO pro
      efetivo/pot desse spot (mesmo solver de Nash usado na abertura) —
      não a range real e desconhecida desse vilão específico.
    - chip EV, não ICM.
    """
    row = conn.execute(
        """SELECT tournament_id, hero, hero_cards, hero_position, hero_stack_bb,
                  bb, button_seat, ts
           FROM hands WHERE site=? AND hand_id=?""",
        (site, hand_id),
    ).fetchone()
    if row is None:
        return None
    tid, hero, hero_cards_s, hero_pos, hero_stack_bb, bb, button_seat, ts = row
    if not hero or not hero_cards_s or not hero_pos or not bb:
        return None

    seats = [Seat(seat_no, player, stack) for seat_no, player, stack in conn.execute(
        "SELECT seat_no, player, stack FROM seats WHERE site=? AND hand_id=?",
        (site, hand_id))]
    if not seats:
        return None
    stack_by_player = {s.player: s.stack for s in seats}

    acts = conn.execute(
        """SELECT player, action, amount, all_in FROM actions
           WHERE site=? AND hand_id=? AND street='preflop' ORDER BY ord""",
        (site, hand_id),
    ).fetchall()

    dead: dict[str, int] = {}
    pot_before = 0
    shover: str | None = None
    hero_action: str | None = None
    for player, action, amount, all_in in acts:
        if action in ("post_sb", "post_bb", "post_ante"):
            dead[player] = dead.get(player, 0) + amount
            pot_before += amount
            continue
        if shover is None:
            # primeira ação voluntária da mão: só é o spot que buscamos
            # se já for um all-in (senão é abertura normal, coberta por
            # analyze_hand_row, ou limp, fora de escopo aqui).
            if not all_in or player == hero:
                return None
            shover = player
            continue
        if player == hero:
            hero_action = action
            break
        if action in ("raise", "bet", "call", "allin"):
            return None  # terceiro jogador entrou antes do herói: multiway, fora de escopo
        # fold de outros jogadores entre o shove e o herói: ok, continua

    if shover is None or hero_action not in ("fold", "call"):
        return None

    stub = Hand(site="", hand_id="", tournament_id="", timestamp=None, level=None,
                sb=0, bb=bb, ante=0, buyin=None, currency=None, table_name=None,
                max_players=None, button_seat=button_seat, seats=seats)
    positions = {seat.player: label for label, seat in (stub.position_order() or [])}
    shover_stack = stack_by_player.get(shover)
    if shover_stack is None:
        return None

    hero_dead = dead.get(hero, 0)
    shover_dead = dead.get(shover, 0)
    hero_remaining_bb = hero_stack_bb - hero_dead / bb
    shover_remaining_bb = (shover_stack - shover_dead) / bb
    effective_bb = min(hero_remaining_bb, shover_remaining_bb)
    pot_bb = pot_before / bb
    if effective_bb <= 1 or effective_bb > max_bb:
        return None

    hero_cards = eq.parse_hand(hero_cards_s)
    if len(hero_cards) != 2:
        return None

    result = _cached_solve(round(effective_bb * 2) / 2, round(pot_bb * 4) / 4)
    if precise:
        equity_vs_range = eq.equity_hand_vs_range(
            hero_cards, result.shove_classes, trials_per_class=trials_final)
    else:
        hcls = eq.class_of(hero_cards)
        equity_vs_range = eq.equity_class_vs_range(hcls, result.shove_classes, _matrix())
    ev_call_bb = equity_vs_range * (pot_bb + 2 * effective_bb) - effective_bb

    hero_decision = "call" if hero_action == "call" else "fold"
    nash_decision = "call" if ev_call_bb > 0 else "fold"
    if hero_decision == "fold" and ev_call_bb > 0:
        ev_lost = ev_call_bb
    elif hero_decision == "call" and ev_call_bb < 0:
        ev_lost = -ev_call_bb
    else:
        ev_lost = 0.0

    return FacingShoveRow(
        site=site, hand_id=hand_id, tournament_id=tid, position=hero_pos,
        shover_position=positions.get(shover, "?"), hero_cards=hero_cards_s,
        effective_bb=round(effective_bb, 1), pot_bb=round(pot_bb, 2),
        hero_decision=hero_decision, nash_decision=nash_decision,
        ev_call_bb=round(ev_call_bb, 2), ev_lost_bb=round(ev_lost, 2), ts=ts,
    )


def analyze_hand_row(conn: sqlite3.Connection, site: str, hand_id: str,
                      max_bb: float = DEFAULT_MAX_BB,
                      precise: bool = False, trials_final: int = 400) -> LeakRow | None:
    """`precise=False` (padrão, usado no relatório em lote): usa a matriz
    classe-vs-classe pré-computada — rápido (lookup), mas ignora as
    cartas exatas do herói (usa a classe, ex. "AKs" independente do naipe).
    `precise=True`: Monte Carlo ao vivo com as cartas exatas do herói —
    mais correto (considera remoção de cartas específicas), mas caro;
    use só pra inspecionar 1 mão por vez, não em lote."""
    row = conn.execute(
        """SELECT tournament_id, hero, hero_cards, hero_position, hero_stack_bb,
                  bb, button_seat, ts
           FROM hands WHERE site=? AND hand_id=?""",
        (site, hand_id),
    ).fetchone()
    if row is None:
        return None
    tid, hero, hero_cards_s, hero_pos, hero_stack_bb, bb, button_seat, ts = row
    if not hero or not hero_cards_s or not hero_pos or hero_pos == "BB" or not bb:
        return None

    seats = [Seat(seat_no, player, stack) for seat_no, player, stack in conn.execute(
        "SELECT seat_no, player, stack FROM seats WHERE site=? AND hand_id=?",
        (site, hand_id))]
    if not seats:
        return None  # mão importada antes da tabela `seats` existir — precisa reimportar
    bb_seat = _bb_seat(seats, button_seat)
    if bb_seat is None or bb_seat.player == hero:
        return None

    acts = conn.execute(
        """SELECT player, action, amount, all_in FROM actions
           WHERE site=? AND hand_id=? AND street='preflop' ORDER BY ord""",
        (site, hand_id),
    ).fetchall()

    dead_bb = {}  # player -> fichas postadas (ante/sb/bb) até agora
    pot_before = 0
    hero_action = None
    unopened = True
    for player, action, amount, all_in in acts:
        if action in ("post_sb", "post_bb", "post_ante"):
            dead_bb[player] = dead_bb.get(player, 0) + amount
            pot_before += amount
            continue
        if player == hero:
            hero_action = action
            break
        if action in ("raise", "bet", "allin", "call"):
            unopened = False
            break  # alguém já entrou antes do herói: fora do escopo (não é mais "abertura")
    if not unopened or hero_action not in ("fold", "raise", "allin"):
        return None

    hero_dead = dead_bb.get(hero, 0)
    bbp_dead = dead_bb.get(bb_seat.player, 0)
    hero_remaining_bb = hero_stack_bb - hero_dead / bb
    bb_remaining_bb = bb_seat.stack / bb - bbp_dead / bb
    effective_bb = min(hero_remaining_bb, bb_remaining_bb)
    pot_bb = pot_before / bb
    if effective_bb <= 1 or effective_bb > max_bb:
        return None

    hero_cards = eq.parse_hand(hero_cards_s)
    if len(hero_cards) != 2:
        return None  # não é Hold'em (ex.: mão Omaha que escapou do filtro do parser)
    result = _cached_solve(round(effective_bb * 2) / 2, round(pot_bb * 4) / 4)
    p_call = result.call_pct / 100
    if precise:
        ev_push_bb, _equity = nash.ev_shove_bb(
            hero_cards, result.call_classes, effective_bb, pot_bb,
            call_pct=p_call, trials_per_class=trials_final)
    else:
        hcls = eq.class_of(hero_cards)
        equity_vs_range = eq.equity_class_vs_range(hcls, result.call_classes, _matrix())
        ev_push_bb = (1 - p_call) * pot_bb + p_call * (
            equity_vs_range * (pot_bb + 2 * effective_bb) - effective_bb)

    hero_decision = "push" if hero_action in ("raise", "allin") else "fold"
    nash_decision = "push" if ev_push_bb > 0 else "fold"
    if hero_decision == "fold" and ev_push_bb > 0:
        ev_lost = ev_push_bb
    elif hero_decision == "push" and ev_push_bb < 0:
        ev_lost = -ev_push_bb
    else:
        ev_lost = 0.0

    return LeakRow(
        site=site, hand_id=hand_id, tournament_id=tid, position=hero_pos,
        hero_cards=hero_cards_s, effective_bb=round(effective_bb, 1),
        pot_bb=round(pot_bb, 2), hero_decision=hero_decision,
        nash_decision=nash_decision, ev_push_bb=round(ev_push_bb, 2),
        ev_lost_bb=round(ev_lost, 2), ts=ts,
    )


def analyze_all(conn: sqlite3.Connection, bb_min: float = 5, bb_max: float = DEFAULT_MAX_BB,
                 progress=None) -> list[LeakRow]:
    """Roda o solver sobre todo spot de abertura já importado com stack
    efetivo dentro de [bb_min, bb_max].

    Otimização: 3 queries batch em vez de N×3 queries individuais.
    Para 260 mãos, reduz ~780 roundtrips ao Postgres para 3.
    `progress(i, total)` opcional.
    """
    # ── 1. Buscar todas as mãos candidatas ──────────────────────────────────
    hand_rows = conn.execute(
        """SELECT site, hand_id, tournament_id, hero, hero_cards, hero_position,
                  hero_stack_bb, bb, button_seat, ts
           FROM hands
           WHERE hero_position IS NOT NULL
             AND hero_position != 'BB'
             AND hero_stack_bb BETWEEN ? AND ?""",
        (bb_min, bb_max + 5),  # margem: stack efetivo real pode ser < hero_stack_bb
    ).fetchall()

    if not hand_rows:
        return []

    hand_map: dict[tuple, tuple] = {(r[0], r[1]): r for r in hand_rows}

    # ── 2. Buscar todos os assentos das mãos candidatas (1 query) ───────────
    seat_rows = conn.execute(
        """SELECT s.site, s.hand_id, s.seat_no, s.player, s.stack
           FROM seats s
           JOIN (
               SELECT site, hand_id FROM hands
               WHERE hero_position IS NOT NULL
                 AND hero_position != 'BB'
                 AND hero_stack_bb BETWEEN ? AND ?
           ) h ON s.site = h.site AND s.hand_id = h.hand_id""",
        (bb_min, bb_max + 5),
    ).fetchall()

    seats_map: dict[tuple, list] = defaultdict(list)
    for site, hand_id, seat_no, player, stack in seat_rows:
        seats_map[(site, hand_id)].append(Seat(seat_no, player, stack))

    # ── 3. Buscar todas as ações preflop das mãos candidatas (1 query) ──────
    action_rows = conn.execute(
        """SELECT a.site, a.hand_id, a.player, a.action, a.amount, a.all_in
           FROM actions a
           JOIN (
               SELECT site, hand_id FROM hands
               WHERE hero_position IS NOT NULL
                 AND hero_position != 'BB'
                 AND hero_stack_bb BETWEEN ? AND ?
           ) h ON a.site = h.site AND a.hand_id = h.hand_id
           WHERE a.street = 'preflop'
           ORDER BY a.site, a.hand_id, a.ord""",
        (bb_min, bb_max + 5),
    ).fetchall()

    actions_map: dict[tuple, list] = defaultdict(list)
    for site, hand_id, player, action, amount, all_in in action_rows:
        actions_map[(site, hand_id)].append((player, action, amount, all_in))

    # ── 4. Processar cada mão em memória (zero queries adicionais) ───────────
    out = []
    total = len(hand_map)
    for i, ((site, hand_id), r) in enumerate(hand_map.items()):
        if progress:
            progress(i, total)
        _, _, tid, hero, hero_cards_s, hero_pos, hero_stack_bb, bb, button_seat, ts = r

        if not hero or not hero_cards_s or not hero_pos or hero_pos == "BB" or not bb:
            continue

        seats = seats_map.get((site, hand_id))
        if not seats:
            continue

        bb_seat = _bb_seat(seats, button_seat)
        if bb_seat is None or bb_seat.player == hero:
            continue

        acts = actions_map.get((site, hand_id), [])

        dead_bb: dict[str, float] = {}
        pot_before = 0.0
        hero_action = None
        unopened = True
        for player, action, amount, all_in in acts:
            if action in ("post_sb", "post_bb", "post_ante"):
                dead_bb[player] = dead_bb.get(player, 0) + amount
                pot_before += amount
                continue
            if player == hero:
                hero_action = action
                break
            if action in ("raise", "bet", "allin", "call"):
                unopened = False
                break

        if not unopened or hero_action not in ("fold", "raise", "allin"):
            continue

        hero_dead = dead_bb.get(hero, 0)
        bbp_dead = dead_bb.get(bb_seat.player, 0)
        hero_remaining_bb = hero_stack_bb - hero_dead / bb
        bb_remaining_bb = bb_seat.stack / bb - bbp_dead / bb
        effective_bb = min(hero_remaining_bb, bb_remaining_bb)
        pot_bb = pot_before / bb
        if effective_bb <= 1 or effective_bb > bb_max:
            continue

        hero_cards = eq.parse_hand(hero_cards_s)
        if len(hero_cards) != 2:
            continue

        result = _cached_solve(round(effective_bb * 2) / 2, round(pot_bb * 4) / 4)
        p_call = result.call_pct / 100
        hcls = eq.class_of(hero_cards)
        equity_vs_range = eq.equity_class_vs_range(hcls, result.call_classes, _matrix())
        ev_push_bb = (1 - p_call) * pot_bb + p_call * (
            equity_vs_range * (pot_bb + 2 * effective_bb) - effective_bb)

        hero_decision = "push" if hero_action in ("raise", "allin") else "fold"
        nash_decision = "push" if ev_push_bb > 0 else "fold"
        if hero_decision == "fold" and ev_push_bb > 0:
            ev_lost = ev_push_bb
        elif hero_decision == "push" and ev_push_bb < 0:
            ev_lost = -ev_push_bb
        else:
            ev_lost = 0.0

        out.append(LeakRow(
            site=site, hand_id=hand_id, tournament_id=tid, position=hero_pos,
            hero_cards=hero_cards_s, effective_bb=round(effective_bb, 1),
            pot_bb=round(pot_bb, 2), hero_decision=hero_decision,
            nash_decision=nash_decision, ev_push_bb=round(ev_push_bb, 2),
            ev_lost_bb=round(ev_lost, 2), ts=ts,
        ))

    return out


def summarize(rows: list[LeakRow]) -> dict:
    total_lost = sum(r.ev_lost_bb for r in rows)
    leaks = [r for r in rows if r.ev_lost_bb > 0]
    by_position: dict[str, dict] = {}
    for r in rows:
        p = by_position.setdefault(r.position, {"spots": 0, "ev_lost_bb": 0.0, "leaks": 0})
        p["spots"] += 1
        p["ev_lost_bb"] += r.ev_lost_bb
        if r.ev_lost_bb > 0:
            p["leaks"] += 1
    return {
        "spots": len(rows),
        "total_ev_lost_bb": round(total_lost, 1),
        "leak_spots": len(leaks),
        "by_position": {k: {**v, "ev_lost_bb": round(v["ev_lost_bb"], 1)}
                         for k, v in by_position.items()},
        "worst": sorted(leaks, key=lambda r: -r.ev_lost_bb)[:20],
        "rows": rows,
    }


def accuracy_by_period(rows: list[LeakRow], period: str = "month") -> list[dict]:
    """Agrupa os spots já analisados por mês/semana/dia (extraído de
    `ts`) e calcula % de decisões corretas — a série real (não sintética)
    por trás do gráfico de evolução Push/Fold."""
    fmt = {"day": lambda d: d[:10], "week": lambda d: d[:10],
           "month": lambda d: d[:7]}[period]
    buckets: dict[str, list[LeakRow]] = {}
    for r in rows:
        if not r.ts:
            continue
        buckets.setdefault(fmt(r.ts), []).append(r)
    out = []
    for key in sorted(buckets):
        rs = buckets[key]
        correct = sum(1 for r in rs if r.ev_lost_bb == 0)
        out.append({
            "period": key, "spots": len(rs), "correct": correct,
            "accuracy_pct": round(correct / len(rs) * 100, 1),
            "ev_lost_bb": round(sum(r.ev_lost_bb for r in rs), 1),
        })
    return out
