"""Parser para hand histories de torneio do PokerStars.

Convenção interna: Action.amount = fichas efetivamente movidas para o
pote naquela ação. Em "raises X to Y", o valor movido é Y menos o que o
jogador já tinha investido na street.
"""
import re
from collections import defaultdict
from ..models import Hand, Seat, Action

HEADER = re.compile(
    r"PokerStars (?:Hand|Game) #(\d+): Tournament #(\d+), "
    r"(?:(?P<buyin>[\$€£R]\$?[\d.,]+)\+(?P<rake>[\$€£R]\$?[\d.,]+)(?:\+(?P<bounty>[\$€£R]\$?[\d.,]+))?\s*(?P<cur>[A-Z]{3})?|Freeroll)"
    r".*?Level (?P<level>[IVXL\d]+) \((?P<sb>\d+)/(?P<bb>\d+)\) - (?P<ts>.+)$"
)
TABLE = re.compile(r"^Table '(.+?)' (\d+)-max Seat #(\d+) is the button")
SEAT = re.compile(r"^Seat (\d+): (.+?) \((\d+) in chips(?:, .*)?\)")
ANTE = re.compile(r"^(.+?): posts the ante (\d+)")
SB = re.compile(r"^(.+?): posts small blind (\d+)")
BB = re.compile(r"^(.+?): posts big blind (\d+)")
DEALT = re.compile(r"^Dealt to (.+?) \[(.+?)\]")
STREET = re.compile(r"^\*\*\* (FLOP|TURN|RIVER) \*\*\*.*\[([^\]]+)\](?: \[([^\]]+)\])?")
HOLE = re.compile(r"^\*\*\* HOLE CARDS \*\*\*")
SUMMARY = re.compile(r"^\*\*\* SUMMARY \*\*\*")
FOLD = re.compile(r"^(.+?): folds")
CHECK = re.compile(r"^(.+?): checks")
CALL = re.compile(r"^(.+?): calls (\d+)( and is all-in)?")
BET = re.compile(r"^(.+?): bets (\d+)( and is all-in)?")
RAISE = re.compile(r"^(.+?): raises (\d+) to (\d+)( and is all-in)?")
COLLECT = re.compile(r"^(.+?) collected (\d+) from (?:the )?(?:main |side )?pot")
UNCALLED = re.compile(r"^Uncalled bet \((\d+)\) returned to (.+)$")

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


def _roman(s: str) -> int:
    if s.isdigit():
        return int(s)
    total, prev = 0, 0
    for ch in reversed(s):
        v = ROMAN.get(ch, 0)
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


def _money(s: str) -> float:
    return float(re.sub(r"[^\d.]", "", s.replace(",", "")))


def split_hands(text: str) -> list[str]:
    idx = [m.start() for m in re.finditer(r"PokerStars (?:Hand|Game) #", text)]
    return [text[idx[i]:(idx[i + 1] if i + 1 < len(idx) else len(text))].strip()
            for i in range(len(idx))]


def parse_hand(block: str) -> Hand | None:
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if not lines:
        return None
    m = HEADER.search(lines[0])
    if not m:
        return None

    buyin = None
    cur = m.group("cur")
    if m.group("buyin"):
        buyin = _money(m.group("buyin")) + _money(m.group("rake"))
        if m.group("bounty"):
            buyin += _money(m.group("bounty"))

    hand = Hand(
        site="pokerstars",
        hand_id=m.group(1),
        tournament_id=m.group(2),
        timestamp=m.group("ts").strip(),
        level=_roman(m.group("level")),
        sb=int(m.group("sb")), bb=int(m.group("bb")), ante=0,
        buyin=buyin, currency=cur,
        table_name=None, max_players=None, button_seat=0,
    )

    street = "preflop"
    order = 0
    board: list[str] = []
    street_paid: dict[str, int] = defaultdict(int)
    in_summary = False

    def add(player, action, amount=0, all_in=False):
        nonlocal order
        order += 1
        hand.actions.append(Action(street=street, player=player, action=action,
                                   amount=amount, all_in=all_in, order=order))

    for line in lines[1:]:
        if SUMMARY.match(line):
            in_summary = True
            continue
        if in_summary:
            continue
        mm = TABLE.match(line)
        if mm:
            hand.table_name = mm.group(1)
            hand.max_players = int(mm.group(2))
            hand.button_seat = int(mm.group(3))
            continue
        mm = SEAT.match(line)
        if mm:
            hand.seats.append(Seat(int(mm.group(1)), mm.group(2), int(mm.group(3))))
            continue
        mm = ANTE.match(line)
        if mm:
            hand.ante = max(hand.ante, int(mm.group(2)))
            add(mm.group(1), "post_ante", int(mm.group(2)))
            continue
        mm = SB.match(line)
        if mm:
            add(mm.group(1), "post_sb", int(mm.group(2)))
            street_paid[mm.group(1)] += int(mm.group(2))
            continue
        mm = BB.match(line)
        if mm:
            add(mm.group(1), "post_bb", int(mm.group(2)))
            street_paid[mm.group(1)] += int(mm.group(2))
            continue
        if HOLE.match(line):
            street = "preflop"
            continue
        mm = DEALT.match(line)
        if mm:
            hand.hero = mm.group(1)
            hand.hero_cards = mm.group(2)
            continue
        mm = STREET.match(line)
        if mm:
            street = mm.group(1).lower()
            street_paid.clear()
            cards = mm.group(2).split()
            extra = mm.group(3)
            if street == "flop":
                board = cards
            else:
                board = cards + ([extra] if extra else [])
                if extra is None and len(cards) > len(board):
                    board = cards
                # linha TURN/RIVER traz board completo + carta nova
                board = cards + (extra.split() if extra else [])
            continue
        mm = RAISE.match(line)
        if mm:
            player, to_amt = mm.group(1), int(mm.group(3))
            moved = to_amt - street_paid[player]
            street_paid[player] = to_amt
            add(player, "raise", moved, all_in=bool(mm.group(4)))
            continue
        mm = BET.match(line)
        if mm:
            add(mm.group(1), "bet", int(mm.group(2)), all_in=bool(mm.group(3)))
            street_paid[mm.group(1)] += int(mm.group(2))
            continue
        mm = CALL.match(line)
        if mm:
            add(mm.group(1), "call", int(mm.group(2)), all_in=bool(mm.group(3)))
            street_paid[mm.group(1)] += int(mm.group(2))
            continue
        mm = CHECK.match(line)
        if mm:
            add(mm.group(1), "check")
            continue
        mm = FOLD.match(line)
        if mm:
            add(mm.group(1), "fold")
            continue
        mm = UNCALLED.match(line)
        if mm:
            # devolve fichas: registra como "win" técnico para fechar contas
            add(mm.group(2).strip(), "win", int(mm.group(1)))
            continue
        mm = COLLECT.match(line)
        if mm:
            add(mm.group(1), "win", int(mm.group(2)))
            continue

    hand.board = " ".join(board) if board else None
    return hand


def parse_file(text: str) -> list[Hand]:
    return [h for h in (parse_hand(b) for b in split_hands(text)) if h]
