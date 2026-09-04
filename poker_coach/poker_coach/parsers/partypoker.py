"""Parser para hand histories do PartyPoker (formato texto exportado
pelo 'My Game' -> Export Hands, anonimizado: Hero / Player1..N).

Convenção interna: Action.amount = fichas efetivamente movidas para o
pote naquela ação (não o valor "raise to"). No texto do PartyPoker,
"raises X to Y" já reporta X como o incremento (não o total), então
nenhuma conversão é necessária como no PokerStars.

O resultado líquido de cada jogador na mão NÃO vem de uma linha
"wins X chips" (essa sala não emite uma) — vem do "** Summary **",
onde cada jogador aparece como "Nome balance N, ...". net = balance
final - stack inicial (visto em "Seat X: Nome (stack)"). Essa
abordagem também absorve corretamente side pots, potes divididos e
sobras devolvidas sem precisar interpretá-los explicitamente.
"""
import re
from ..models import Hand, Seat, Action

GAME_HEADER = re.compile(r"\*{3,}\s*Hand History For Game\s+(\S+?)\s*\*{3,}", re.I)

# Duas variantes de cabeçalho já vistas em exports do PartyPoker:
#   antiga:  "NL Texas Hold'em ... Trny: 148228870 Level: 5  Blinds-Antes(250/500 -50) - Saturday, January 18, 20:38:02 CET 2020"
#   atual:   "30000/60000 Tourney Texas Holdem Game Table (NL) (MTT Tournament #420849778) (Buyin $0.0 + $0.0) - Fri May 29 23:31:41 EDT 2026"
TRNY_RE = re.compile(r"Trny:\s*(\d+)")
TRNY_RE2 = re.compile(r"Tournament\s*#(\d+)")
LEVEL_RE = re.compile(r"Level:\s*(\d+)")
BUYIN_RE = re.compile(r"([€$£R]\$?)\s?([\d.,]+)\s*(USD|EUR|GBP|BRL)?\s*Buy-?in", re.I)
BUYIN_RE2 = re.compile(r"\(Buyin\s*([€$£R]\$?)\s*([\d.,]+)\s*\+\s*[€$£R]?\$?\s*([\d.,]+)\s*\)", re.I)
BLINDS_ANTE_RE = re.compile(r"Blinds-Antes\(\s*([\d,]+)\s*/\s*([\d,]+)\s*-\s*([\d,]+)\s*\)")
BLINDS_RE = re.compile(r"Blinds\(\s*([\d,]+)\s*/\s*([\d,]+)\s*\)")
BLINDS_RE2 = re.compile(r"^([\d,]+)\s*/\s*([\d,]+)\s+Tourney", re.I)
DATE_RE = re.compile(r"-\s+\w+,\s+(\w+)\s+(\d+),?\s+(\d{2}:\d{2}:\d{2})\s+(\w+)\s+(\d{4})")
DATE_RE2 = re.compile(r"-\s+\w+\s+(\w+)\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\s+(\w+)\s+(\d{4})\s*$")

TABLE_RE = re.compile(r"^Table\s+(.*?)\s*(?:\(Real Money\))?\s*(?:--.*)?$")
BUTTON_RE = re.compile(r"Seat (\d+) is the button")
TOTAL_RE = re.compile(r"Total number of players\s*:\s*(\d+)\s*/\s*(\d+)")
SEAT_RE = re.compile(r"^Seat (\d+):\s*(.+?)\s*\(\s*([\d,.]+)\s*\)")

POST_SB = re.compile(r"^(.+?) posts small blind [\[\(]?([\d,]+)[\]\)]?")
POST_BB = re.compile(r"^(.+?) posts big blind [\[\(]?([\d,]+)[\]\)]?")
POST_ANTE = re.compile(r"^(.+?) posts ante [\[\(]?([\d,]+)[\]\)]?")
DEALT = re.compile(r"^Dealt to (.+?)\s*\[\s*(.+?)\s*\]")
STREET_MARK = re.compile(r"^\*\* Dealing (Flop|Turn|River) \*\*\s*:?\s*\[\s*(.+?)\s*\]")
HOLE_MARK = re.compile(r"^\*\* Dealing down cards \*\*")
SUMMARY_MARK = re.compile(r"^\*\*\s*Summary\s*\*\*", re.I)

# Exports do "My Game" podem misturar outras variantes (Omaha Hi,
# Omaha Hi/Lo, Stud...) na mesma sessão — o resto do sistema (posições,
# equity, push/fold) assume Hold'em de 2 cartas, então filtramos aqui.
# Casa com os dois formatos de cabeçalho conhecidos: "NL Texas Hold'em..."
# (antigo) e "... Tourney Texas Holdem Game Table..." (atual).
HOLDEM_GAME_RE = re.compile(r"Texas\s+Hold'?em", re.I)

FOLD = re.compile(r"^(.+?) folds")
CHECK = re.compile(r"^(.+?) checks")
CALL = re.compile(r"^(.+?) calls [\[\(]?([\d,]+)[\]\)]?")
BET = re.compile(r"^(.+?) bets [\[\(]?([\d,]+)[\]\)]?")
RAISE = re.compile(r"^(.+?) raises [\[\(]?([\d,]+)[\]\)]?")
# "Nome is all-In." (sem valor, marcador que segue a ação real) ou,
# em outras variantes, "Nome is all-in [N]" com valor embutido.
ALLIN = re.compile(r"^(.+?) is all-?in\.?\s*(?:\[?([\d,]+)\]?)?\s*$", re.I)
WIN = re.compile(r"^(.+?) wins ([\d,]+) chips")
WIN_SPLIT = re.compile(r"^(.+?) wins ([\d,]+) chips from the (?:main|side) pot")
SHOW = re.compile(r"^(.+?) shows \[\s*(.+?)\s*\]")
# Linha de resultado no ** Summary **, ex.:
#   "Player3 balance 4169055, bet 899196, collected 1967344, net +1068148[...]"
#   "Player1 balance 10166, lost 7500 (folded)"
#   "Player6 balance 1264090, sits out"
# ATENÇÃO: "balance" NÃO é sempre o stack final — quando o jogador vai
# all-in e vence, "balance" é o stack intermediário (0, antes de
# receber o pote) e o "net +N" explícito é o valor correto. Por isso
# lemos net/lost diretamente do texto em vez de subtrair do stack
# inicial.
BALANCE_RE = re.compile(r"^(.+?) balance (-?[\d,]+),")
NET_RE = re.compile(r"net ([+-][\d,]+)")
LOST_RE = re.compile(r"lost ([\d,]+)")
# cartas de showdown: colchete IMEDIATAMENTE após o número de net/lost
# (com no máx. espaços entre eles) — o segundo colchete da linha (com o
# nome da mão, tipo "a straight, six to ten -- ...") não é capturado
# porque essa regex só casa a partir do início de `tail` (.match, não
# .search) e para no primeiro "]".
SHOWDOWN_CARDS_RE = re.compile(r"^\s*\[\s*([^\]]+?)\s*\]")

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
MONTHS_ABBR = {m[:3]: i for m, i in MONTHS.items()}


def _num(s: str) -> int:
    return int(s.replace(",", "").split(".")[0])


def split_hands(text: str) -> list[str]:
    """Divide o arquivo em blocos, um por mão."""
    idx = [m.start() for m in GAME_HEADER.finditer(text)]
    blocks = []
    for i, start in enumerate(idx):
        end = idx[i + 1] if i + 1 < len(idx) else len(text)
        blocks.append(text[start:end].strip())
    return blocks


def _parse_date(header: str) -> str | None:
    dt = DATE_RE.search(header)
    if dt:
        mon, day, hms, _tz, year = dt.groups()
        if mon in MONTHS:
            return f"{year}-{MONTHS[mon]:02d}-{int(day):02d}T{hms}"
    dt = DATE_RE2.search(header)
    if dt:
        mon, day, hms, _tz, year = dt.groups()
        mnum = MONTHS.get(mon) or MONTHS_ABBR.get(mon[:3])
        if mnum:
            return f"{year}-{mnum:02d}-{int(day):02d}T{hms}"
    return None


def parse_hand(block: str) -> Hand | None:
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if not lines:
        return None
    m = GAME_HEADER.search(lines[0])
    if not m:
        return None
    hand_id = m.group(1)

    header = lines[1] if len(lines) > 1 else ""
    if not HOLDEM_GAME_RE.search(header):
        return None  # Omaha/Stud/outra variante: fora do escopo (ver HOLDEM_GAME_RE)

    trny = TRNY_RE.search(header) or TRNY_RE2.search(header)
    level = LEVEL_RE.search(header)
    buyin = BUYIN_RE.search(header)
    buyin2 = None if buyin else BUYIN_RE2.search(header)
    ba = BLINDS_ANTE_RE.search(header)
    bl = BLINDS_RE.search(header) or BLINDS_RE2.search(header)

    sb = bb = ante = 0
    if ba:
        sb, bb, ante = _num(ba.group(1)), _num(ba.group(2)), _num(ba.group(3))
    elif bl:
        sb, bb = _num(bl.group(1)), _num(bl.group(2))

    if buyin:
        buyin_val = float(buyin.group(2).replace(",", "."))
        currency = buyin.group(3) or buyin.group(1)
    elif buyin2:
        buyin_val = float(buyin2.group(2).replace(",", ".")) + float(buyin2.group(3).replace(",", "."))
        currency = buyin2.group(1)
    else:
        buyin_val = None
        currency = None

    hand = Hand(
        site="partypoker",
        hand_id=hand_id,
        tournament_id=trny.group(1) if trny else "unknown",
        timestamp=_parse_date(header),
        level=int(level.group(1)) if level else None,
        sb=sb, bb=bb, ante=ante,
        buyin=buyin_val,
        currency=currency,
        table_name=None,
        max_players=None,
        button_seat=0,
    )

    street = "preflop"
    order = 0
    board_cards: list[str] = []
    seen_players: set[str] = set()
    in_summary = False

    def add(player, action, amount=0, all_in=False):
        nonlocal order
        order += 1
        hand.actions.append(Action(street=street, player=player, action=action,
                                   amount=amount, all_in=all_in, order=order))

    def mark_last_allin(player):
        for a in reversed(hand.actions):
            if a.player == player:
                a.all_in = True
                return

    for line in lines[1:]:
        mm = BUTTON_RE.search(line)
        if mm:
            hand.button_seat = int(mm.group(1))

        if in_summary:
            mm = BALANCE_RE.match(line)
            if mm:
                name = mm.group(1).strip()
                net_m = NET_RE.search(line)
                lost_m = LOST_RE.search(line)
                tail = ""
                if net_m:
                    net = int(net_m.group(1).replace(",", ""))
                    tail = line[net_m.end():]
                elif lost_m:
                    net = -_num(lost_m.group(1))
                    tail = line[lost_m.end():]
                else:
                    net = 0  # ex.: "sits out", sem fichas movidas
                hand.results[name] = net
                # cartas de showdown: só aparecem se o PRÓXIMO token não-
                # espaço depois do número for "[" — "(folded)"/"sits out"
                # não têm colchete ali, então não capturam nada.
                cm = SHOWDOWN_CARDS_RE.match(tail)
                if cm:
                    cards_str = " ".join(cm.group(1).replace(",", " ").split())
                    hand.shown_cards[name] = cards_str
            continue

        if SUMMARY_MARK.match(line):
            in_summary = True
            continue

        mm = TABLE_RE.match(line)
        if mm and hand.table_name is None:
            name = mm.group(1).strip()
            if name:
                hand.table_name = name
            continue
        mm = TOTAL_RE.search(line)
        if mm:
            hand.max_players = int(mm.group(2))
            continue
        mm = SEAT_RE.match(line)
        if mm and "button" not in line:
            name = mm.group(2).strip()
            if name not in seen_players:
                seen_players.add(name)
                hand.seats.append(Seat(int(mm.group(1)), name, _num(mm.group(3))))
            continue
        mm = STREET_MARK.match(line)
        if mm:
            street = mm.group(1).lower()
            cards = [c.strip() for c in mm.group(2).replace(",", " ").split()]
            board_cards.extend(cards)
            continue
        if HOLE_MARK.match(line):
            street = "preflop"
            continue
        mm = DEALT.match(line)
        if mm:
            hand.hero = mm.group(1).strip()
            hand.hero_cards = " ".join(mm.group(2).replace(",", " ").split())
            continue
        mm = POST_SB.match(line)
        if mm:
            add(mm.group(1).strip(), "post_sb", _num(mm.group(2)))
            continue
        mm = POST_BB.match(line)
        if mm:
            add(mm.group(1).strip(), "post_bb", _num(mm.group(2)))
            continue
        mm = POST_ANTE.match(line)
        if mm:
            amt = _num(mm.group(2))
            hand.ante = max(hand.ante, amt)
            add(mm.group(1).strip(), "post_ante", amt)
            continue
        mm = ALLIN.match(line)
        if mm:
            player = mm.group(1).strip()
            if mm.group(2):
                add(player, "allin", _num(mm.group(2)), all_in=True)
            else:
                mark_last_allin(player)
            continue
        mm = RAISE.match(line)
        if mm:
            add(mm.group(1).strip(), "raise", _num(mm.group(2)))
            continue
        mm = BET.match(line)
        if mm:
            add(mm.group(1).strip(), "bet", _num(mm.group(2)))
            continue
        mm = CALL.match(line)
        if mm:
            add(mm.group(1).strip(), "call", _num(mm.group(2)))
            continue
        mm = CHECK.match(line)
        if mm:
            add(mm.group(1).strip(), "check")
            continue
        mm = FOLD.match(line)
        if mm:
            add(mm.group(1).strip(), "fold")
            continue
        mm = WIN_SPLIT.match(line) or WIN.match(line)
        if mm:
            add(mm.group(1).strip(), "win", _num(mm.group(2)))
            continue
        mm = SHOW.match(line)
        if mm:
            add(mm.group(1).strip(), "show")
            continue

    hand.board = " ".join(board_cards) if board_cards else None
    return hand


def parse_file(text: str) -> list[Hand]:
    hands = []
    for block in split_hands(text):
        h = parse_hand(block)
        if h is not None:
            hands.append(h)
    return hands
