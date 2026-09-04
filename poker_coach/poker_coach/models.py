"""Modelo de dados central: Torneio -> Mão -> Ação.

Tudo normalizado para permitir análise em BB e, futuramente,
os motores de Push/Fold e ICM (Fase 4).
"""
from dataclasses import dataclass, field
from typing import Optional


STREETS = ("preflop", "flop", "turn", "river")

# Ações normalizadas entre salas
ACTIONS = (
    "post_sb", "post_bb", "post_ante", "post_dead",
    "fold", "check", "call", "bet", "raise", "allin",
    "show", "muck", "win",
)


@dataclass
class Seat:
    seat_no: int
    player: str
    stack: int  # em fichas, no início da mão


@dataclass
class Action:
    street: str          # preflop / flop / turn / river
    player: str
    action: str          # um de ACTIONS
    amount: int = 0      # fichas envolvidas na ação
    all_in: bool = False
    order: int = 0       # ordem global da ação na mão


@dataclass
class Hand:
    site: str                    # 'partypoker' | 'pokerstars'
    hand_id: str
    tournament_id: str
    timestamp: Optional[str]     # ISO 8601 quando possível
    level: Optional[int]
    sb: int
    bb: int
    ante: int
    buyin: Optional[float]       # em moeda, se presente no header
    currency: Optional[str]
    table_name: Optional[str]
    max_players: Optional[int]
    button_seat: int
    seats: list[Seat] = field(default_factory=list)
    hero: Optional[str] = None
    hero_cards: Optional[str] = None      # ex.: "Ah Kd"
    board: Optional[str] = None           # ex.: "2s 7h Jd 5c 9d"
    actions: list[Action] = field(default_factory=list)
    # net chips por jogador, quando a sala reporta o saldo final na mão
    # (ex.: PartyPoker: "Player balance N, ..." no ** Summary **) em vez
    # de linhas explícitas de "wins X chips". Quando presente, tem
    # prioridade sobre o cálculo derivado de actions.
    results: dict[str, int] = field(default_factory=dict)
    # cartas reveladas no showdown (player -> "Ah Kd"), quando a sala
    # mostra — no PartyPoker isso vem embutido no "** Summary **", não
    # numa linha "shows" separada como no PokerStars.
    shown_cards: dict[str, str] = field(default_factory=dict)

    # ---- Derivados úteis para análise ----
    def hero_seat(self) -> Optional[Seat]:
        for s in self.seats:
            if s.player == self.hero:
                return s
        return None

    def hero_stack_bb(self) -> Optional[float]:
        s = self.hero_seat()
        if s is None or not self.bb:
            return None
        return round(s.stack / self.bb, 2)

    def n_players(self) -> int:
        return len(self.seats)

    def position_order(self) -> Optional[list[tuple[str, "Seat"]]]:
        """Lista (label, Seat) em ordem a partir do botão: BTN, SB, BB, UTG...
        Base compartilhada por hero_position() e por qualquer código que
        precise achar quem está em uma posição específica (ex.: o motor
        de Push/Fold, que precisa do stack da BB para calcular equity/pot).
        """
        occupied = sorted(x.seat_no for x in self.seats)
        n = len(occupied)
        if self.button_seat not in occupied:
            return None
        by_seat_no = {x.seat_no: x for x in self.seats}
        btn_idx = occupied.index(self.button_seat)
        order = [occupied[(btn_idx + i) % n] for i in range(n)]
        if n == 2:  # heads-up: botão é SB
            names = ["SB", "BB"]
        else:
            names = ["BTN", "SB", "BB"]
            rest = n - 3
            mids = []
            labels = ["UTG", "UTG+1", "UTG+2", "MP", "MP+1", "HJ", "CO"]
            if rest > 0:
                mids = labels[:rest]
                if rest >= 2:
                    mids[-1] = "CO"
                if rest >= 3:
                    mids[-2] = "HJ"
            names += mids
        return [(names[i], by_seat_no[seat_no]) for i, seat_no in enumerate(order)]

    def seat_at_position(self, label: str) -> Optional["Seat"]:
        """Ex.: hand.seat_at_position('BB') -> Seat da big blind, ou None."""
        order = self.position_order()
        if order is None:
            return None
        for lbl, seat in order:
            if lbl == label:
                return seat
        return None

    def hero_position(self) -> Optional[str]:
        """Posição do herói relativa ao botão: BTN, SB, BB, UTG, ..., CO."""
        s = self.hero_seat()
        if s is None:
            return None
        order = self.position_order()
        if order is None:
            return None
        for label, seat in order:
            if seat.seat_no == s.seat_no:
                return label
        return None

    def hero_vpip(self) -> bool:
        """Hero colocou fichas voluntariamente no preflop?"""
        for a in self.actions:
            if a.street != "preflop" or a.player != self.hero:
                continue
            if a.action in ("call", "bet", "raise", "allin"):
                return True
        return False

    def hero_pfr(self) -> bool:
        for a in self.actions:
            if a.street != "preflop" or a.player != self.hero:
                continue
            if a.action in ("raise", "allin") and a.action != "call":
                return True
        return False

    def hero_net_chips(self) -> int:
        """Fichas ganhas menos investidas pelo herói na mão.

        Prioriza `results` (saldo final reportado pela sala, robusto a
        potes divididos/side pots/uncalled bets). Sem isso, cai para o
        cálculo por ações (salas que emitem "wins X chips" explícito).
        """
        if self.hero is not None and self.hero in self.results:
            return self.results[self.hero]
        invested = 0
        won = 0
        for a in self.actions:
            if a.player != self.hero:
                continue
            if a.action == "win":
                won += a.amount
            elif a.action in ("post_sb", "post_bb", "post_ante", "post_dead",
                              "call", "bet", "raise", "allin"):
                invested += a.amount
        return won - invested
