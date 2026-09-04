"""Reconstrói o estado completo de uma mão, ação por ação, a partir do
banco (hands + seats + actions + showdowns) — motor do Replayer.

Não depende de re-parsear a hand history: usa só o que já está
persistido, então funciona igual pra PartyPoker/PokerStars uma vez
importadas.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from .models import Hand, Seat

STREET_ORDER = ["preflop", "flop", "turn", "river"]


@dataclass
class ReplayStep:
    order: int
    street: str
    player: str
    position: str | None
    action: str
    amount: int
    all_in: bool
    pot_after: int
    stacks_after: dict[str, int]
    board_so_far: str


@dataclass
class ReplayHand:
    site: str
    hand_id: str
    tournament_id: str
    tournament_name: str | None
    buyin: float | None
    ts: str | None
    sb: int
    bb: int
    ante: int
    button_seat: int
    hero: str | None
    hero_cards: str | None
    seats: list[Seat]
    positions: dict[str, str] = field(default_factory=dict)  # player -> "BTN"/"SB"/...
    seat_order: list[str] = field(default_factory=list)      # jogadores em ordem BTN,SB,BB,...
    board: str | None = None
    shown_cards: dict[str, str] = field(default_factory=dict)
    steps: list[ReplayStep] = field(default_factory=list)
    street_first_index: dict[str, int] = field(default_factory=dict)

    def starting_stacks(self) -> dict[str, int]:
        return {s.player: s.stack for s in self.seats}

    def state_at(self, step_index: int) -> tuple[int, dict[str, int], str]:
        """(pot, stacks, board_so_far) logo APÓS o passo `step_index`
        (step_index=-1 -> estado inicial, antes de qualquer ação)."""
        if step_index < 0 or not self.steps:
            return 0, self.starting_stacks(), ""
        step_index = min(step_index, len(self.steps) - 1)
        s = self.steps[step_index]
        return s.pot_after, s.stacks_after, s.board_so_far


def load(conn: sqlite3.Connection, site: str, hand_id: str) -> ReplayHand | None:
    row = conn.execute(
        """SELECT tournament_id, ts, sb, bb, ante, button_seat, hero, hero_cards, board
           FROM hands WHERE site=? AND hand_id=?""",
        (site, hand_id),
    ).fetchone()
    if row is None:
        return None
    tid, ts, sb, bb, ante, button_seat, hero, hero_cards, board = row

    tname_row = conn.execute(
        "SELECT name, buyin FROM tournaments WHERE site=? AND tournament_id=?",
        (site, tid),
    ).fetchone()
    tname, tbuyin = tname_row if tname_row else (None, None)

    seats = [Seat(seat_no, player, stack) for seat_no, player, stack in conn.execute(
        "SELECT seat_no, player, stack FROM seats WHERE site=? AND hand_id=? ORDER BY seat_no",
        (site, hand_id))]

    stub = Hand(site=site, hand_id=hand_id, tournament_id=tid, timestamp=ts, level=None,
                sb=sb, bb=bb, ante=ante, buyin=None, currency=None, table_name=None,
                max_players=None, button_seat=button_seat, seats=seats)
    order = stub.position_order() or []
    positions = {seat.player: label for label, seat in order}
    seat_order = [seat.player for _label, seat in order]

    shown = dict(conn.execute(
        "SELECT player, cards FROM showdowns WHERE site=? AND hand_id=?", (site, hand_id)))

    board_cards = board.split() if board else []
    board_by_street = {"preflop": [], "flop": board_cards[:3],
                        "turn": board_cards[:4], "river": board_cards[:5]}

    rh = ReplayHand(site=site, hand_id=hand_id, tournament_id=tid, tournament_name=tname,
                     buyin=tbuyin, ts=ts, sb=sb, bb=bb,
                     ante=ante, button_seat=button_seat, hero=hero, hero_cards=hero_cards,
                     seats=seats, positions=positions, seat_order=seat_order,
                     board=board, shown_cards=shown)

    stacks = rh.starting_stacks()
    pot = 0
    acts = conn.execute(
        """SELECT ord, street, player, action, amount, all_in FROM actions
           WHERE site=? AND hand_id=? ORDER BY ord""",
        (site, hand_id),
    ).fetchall()

    for ordn, street, player, action, amount, all_in in acts:
        if street not in rh.street_first_index:
            rh.street_first_index[street] = len(rh.steps)
        if action in ("post_sb", "post_bb", "post_ante", "call", "bet", "raise", "allin"):
            stacks[player] = stacks.get(player, 0) - amount
            pot += amount
        elif action == "win":
            stacks[player] = stacks.get(player, 0) + amount
            pot -= amount
        # fold/check/show: sem mudança de fichas

        rh.steps.append(ReplayStep(
            order=ordn, street=street, player=player, position=positions.get(player),
            action=action, amount=amount, all_in=bool(all_in),
            pot_after=pot, stacks_after=dict(stacks),
            board_so_far=" ".join(board_by_street.get(street, board_cards)),
        ))

    # "Runout" sem ação: quando os jogadores restantes ficam all-in antes
    # do fim (ex.: hero all-in no preflop, vilão paga), a sala só DEALT
    # o resto do board (** Dealing Flop/Turn/River **), sem nenhuma linha
    # de ação — ninguém tem decisão a tomar. Isso deixava a mão "travada"
    # no preflop no replayer, mesmo quando ela foi a showdown com board
    # completo (a rua nunca aparecia em `actions`, só em `hands.board`).
    # Sintetiza um passo por rua faltante, só pra avançar o board/timeline.
    last_order = rh.steps[-1].order if rh.steps else 0
    street_len = {"flop": 3, "turn": 4, "river": 5}
    for street, needed in street_len.items():
        if street in rh.street_first_index or len(board_cards) < needed:
            continue
        last_order += 1
        rh.street_first_index[street] = len(rh.steps)
        rh.steps.append(ReplayStep(
            order=last_order, street=street, player="", position=None,
            action="deal", amount=0, all_in=False, pot_after=pot,
            stacks_after=dict(stacks), board_so_far=" ".join(board_by_street[street]),
        ))

    # Resolução final: salas como o PartyPoker nunca emitem uma ação
    # "wins X chips" (só reportam no Summary) — sem isso o pote nunca
    # seria creditado ao vencedor. `results` (net chips por jogador,
    # persistido à parte) é a fonte de verdade; fechamos a mão ajustando
    # as pilhas pra bater exatamente com starting_stack + net_chips.
    results = dict(conn.execute(
        "SELECT player, net_chips FROM results WHERE site=? AND hand_id=?", (site, hand_id)))
    if results:
        final_stacks = {p: rh.starting_stacks().get(p, 0) + net for p, net in results.items()}
        last_street = rh.steps[-1].street if rh.steps else "preflop"
        last_board = rh.steps[-1].board_so_far if rh.steps else ""
        rh.steps.append(ReplayStep(
            order=(rh.steps[-1].order + 1 if rh.steps else 1), street=last_street,
            player="", position=None, action="resolve", amount=0, all_in=False,
            pot_after=0, stacks_after=final_stacks, board_so_far=last_board,
        ))

    return rh


def list_hands(conn: sqlite3.Connection, *, site: str | None = None,
                tournament_id: str | None = None, position: str | None = None,
                bb_min: float | None = None, bb_max: float | None = None,
                n_players: int | None = None, result: str | None = None,
                tag: str | None = None, q: str | None = None,
                favorite: bool | None = None, showdown: bool | None = None,
                all_in: bool | None = None,
                date_from: str | None = None, date_to: str | None = None,
                limit: int = 200) -> list[dict]:
    """Busca de mãos pro seletor do Replayer (e Modo Estudo) — todos os
    filtros são opcionais e combináveis. `favorite`/`showdown`/`all_in`
    são tri-state (None = todos, True/False = só sim/só não); `result`
    é "win"/"loss"; `q` casa livremente em hand_id, cartas, tags e nota."""
    where = ["1=1"]
    params: list = []
    if site:
        where.append("h.site=?")
        params.append(site)
    if tournament_id:
        where.append("h.tournament_id=?")
        params.append(tournament_id)
    if position:
        where.append("h.hero_position=?")
        params.append(position)
    if bb_min is not None:
        where.append("h.hero_stack_bb>=?")
        params.append(bb_min)
    if bb_max is not None:
        where.append("h.hero_stack_bb<=?")
        params.append(bb_max)
    if n_players is not None:
        where.append("h.n_players=?")
        params.append(n_players)
    if result == "win":
        where.append("h.hero_net_chips>0")
    elif result == "loss":
        where.append("h.hero_net_chips<0")
    if favorite is not None:
        where.append("h.favorite=?")
        params.append(1 if favorite else 0)
    if date_from:
        where.append("h.ts>=?")
        params.append(date_from)
    if date_to:
        where.append("h.ts<=?")
        params.append(date_to + "T23:59:59")
    sd_expr = ("EXISTS (SELECT 1 FROM showdowns sd WHERE sd.site=h.site "
               "AND sd.hand_id=h.hand_id AND sd.player=h.hero)")
    if showdown is True:
        where.append(sd_expr)
    elif showdown is False:
        where.append(f"NOT {sd_expr}")
    ai_expr = ("EXISTS (SELECT 1 FROM actions a WHERE a.site=h.site "
               "AND a.hand_id=h.hand_id AND a.player=h.hero AND a.all_in=1)")
    if all_in is True:
        where.append(ai_expr)
    elif all_in is False:
        where.append(f"NOT {ai_expr}")
    if tag:
        where.append("EXISTS (SELECT 1 FROM tags t WHERE t.site=h.site "
                      "AND t.hand_id=h.hand_id AND t.tag=?)")
        params.append(tag)
    if q:
        like = f"%{q}%"
        where.append(
            "(h.hand_id LIKE ? OR h.hero_cards LIKE ? OR h.board LIKE ? "
            "OR EXISTS (SELECT 1 FROM tags t WHERE t.site=h.site AND t.hand_id=h.hand_id "
            "AND t.tag LIKE ?) "
            "OR EXISTS (SELECT 1 FROM notes nt WHERE nt.site=h.site AND nt.hand_id=h.hand_id "
            "AND nt.text LIKE ?))"
        )
        params += [like, like, like, like, like]

    sql = f"""SELECT h.site, h.hand_id, h.tournament_id, COALESCE(t.name, h.tournament_id),
                     t.buyin, h.ts, h.hero_position, h.hero_cards, h.hero_stack_bb,
                     h.hero_net_chips, h.bb, h.favorite, h.board, h.n_players,
                     {sd_expr} AS showdown, {ai_expr} AS all_in
              FROM hands h LEFT JOIN tournaments t
                ON t.site = h.site AND t.tournament_id = h.tournament_id
              WHERE {' AND '.join(where)}
              ORDER BY h.ts DESC LIMIT ?"""
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [{
        "site": s, "hand_id": hid, "tournament_id": tid, "tournament_name": tname,
        "buyin": buyin, "ts": ts, "position": pos, "hero_cards": cards, "stack_bb": bbv,
        "net_bb": round((net or 0) / bb, 1) if bb else 0, "favorite": bool(fav),
        "board": board, "n_players": nplayers, "showdown": bool(sd), "all_in": bool(ai),
    } for s, hid, tid, tname, buyin, ts, pos, cards, bbv, net, bb, fav, board, nplayers, sd, ai
      in rows]
