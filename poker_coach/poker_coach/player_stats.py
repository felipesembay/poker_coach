"""Estatísticas de estilo de jogo do herói (VPIP, PFR, 3-Bet, Fold to 3-Bet,
ATS, Fold to Steal, C-Bet, Fold to C-Bet) com denominador correto por
métrica — base da tela "Estilo de Jogo" (API: api/routers/play_style.py).

Arquitetura em duas camadas:

1. `load_hand_features(conn)` — lê hands/tournaments/seats/actions UMA vez
   (3 queries, sem N+1) e devolve um DataFrame com uma linha por mão e
   pares de colunas `<métrica>_opp` / `<métrica>` (0/1): "a mão foi uma
   oportunidade?" e "o herói fez a ação?". É a parte cara; a API cacheia.
2. `summarize` / `summarize_by` / `evolution` — agregações baratas (soma de
   flags) sobre o subconjunto filtrado, recalculadas a cada filtro.

POSIÇÃO: NÃO usa `hands.hero_position`. Essa coluna é gravada no import e as
mãos importadas antes da correção de `Hand.position_order` (mesas 4/5-handed
classificadas como "UTG") nunca foram regravadas. Aqui a posição é
recalculada a partir de `seats` + `button_seat` chamando o próprio
`Hand.position_order` — mesma lógica, sem duplicar a regra. Em heads-up o
botão é o próprio small blind (posta o SB, age primeiro no preflop e por
último no pós-flop); `position_order` chama de "SB", aqui vira "BTN/SB" —
categoria própria, pra comparar o jogo HU com o resto do torneio sem
misturar com BTN/SB de mesa cheia.

Definições (todas só com ações preflop/flop, ignorando post_sb/bb/ante):
- VPIP / PFR: oportunidade = herói teve pelo menos uma decisão preflop
  (exclui walks na BB). VPIP = call/raise; PFR = raise.
- 3-Bet: oportunidade = herói decide diante de exatamente 1 raise que não é
  dele (1ª vez na mão). Feito = raise nessa decisão.
- Fold to 3-Bet: herói fez o 1º raise e decide diante de exatamente 2
  raises (a 3-bet). Feito = fold. Open-shove do herói não gera oportunidade.
- ATS: herói em CO/BTN/SB (ou BTN/SB no HU), pote sem limp nem raise antes.
  Feito = raise (limp não conta como steal).
- Fold to Steal: herói na SB/BB, primeira decisão diante de 1 raise vindo
  de CO/BTN/SB, sem nenhum call antes dele. Feito = fold.
- C-Bet: herói foi o último agressor preflop e o flop chega nele sem
  aposta. Feito = bet.
- Fold to C-Bet: agressor preflop é outro jogador, a 1ª ação dele no flop é
  bet com o flop sem aposta até ali, e o herói responde sem raise no meio.
  Feito = fold.
"""
import datetime as dt
from collections import defaultdict

import pandas as pd

from .models import Hand, Seat

POSTS = ("post_sb", "post_bb", "post_ante", "post_dead")
AGGRESSIVE = ("bet", "raise", "allin")
VOLUNTARY = ("call", "bet", "raise", "allin")

POSITION_ORDER = ["UTG", "UTG+1", "UTG+2", "MP", "MP+1", "HJ", "CO",
                  "BTN", "BTN/SB", "SB", "BB"]
STEAL_POSITIONS = {"CO", "BTN", "SB", "BTN/SB"}
BLIND_POSITIONS = {"SB", "BB"}

INF = float("inf")
STACK_RANGES = [
    ("<8 BB", 0, 8), ("8–12 BB", 8, 12), ("12–15 BB", 12, 15),
    ("15–20 BB", 15, 20), ("20–30 BB", 20, 30), ("30+ BB", 30, INF),
]
STACK_LABELS = [r[0] for r in STACK_RANGES]

# chave -> (rótulo, coluna de oportunidade, coluna de ação, explicação)
METRICS = {
    "vpip": ("VPIP", "vpip_opp", "vpip",
             "Mãos em que você colocou fichas voluntariamente no preflop (call/raise) "
             "÷ mãos em que teve alguma decisão preflop (walks na BB não contam)."),
    "pfr": ("PFR", "vpip_opp", "pfr",
            "Mãos com raise preflop ÷ mãos em que teve alguma decisão preflop."),
    "threebet": ("3-Bet", "threebet_opp", "threebet",
                 "Re-raises ÷ vezes em que você decidiu diante de exatamente um raise de outro jogador."),
    "f3b": ("Fold to 3-Bet", "f3b_opp", "f3b",
            "Folds ÷ vezes em que você abriu com raise, levou 3-bet e teve que decidir."),
    "ats": ("ATS", "ats_opp", "ats",
            "Attempt to Steal: raises ÷ vezes em que chegou foldado até você no CO/BTN/SB."),
    "fts": ("Fold to Steal", "fts_opp", "fts",
            "Folds ÷ vezes em que, na SB/BB, você enfrentou só um raise vindo de CO/BTN/SB."),
    "cbet": ("C-Bet", "cbet_opp", "cbet",
             "Bets no flop ÷ flops em que você foi o agressor preflop e a ação chegou em você sem aposta."),
    "fcb": ("Fold to C-Bet", "fcb_opp", "fcb",
            "Folds ÷ vezes em que enfrentou a c-bet do agressor preflop no flop."),
}
FLAG_COLUMNS = sorted({c for _, opp, made, _ in METRICS.values() for c in (opp, made)})


def positions_by_player(button_seat: int, seats: list[Seat]) -> dict[str, str]:
    """{jogador: posição} reusando `Hand.position_order` (fonte única da
    regra de posição relativa ao botão). HU: botão = "BTN/SB"."""
    hand = Hand(site="", hand_id="", tournament_id="", timestamp=None, level=None,
                sb=0, bb=0, ante=0, buyin=None, currency=None, table_name=None,
                max_players=None, button_seat=button_seat, seats=seats)
    order = hand.position_order()
    if order is None:
        return {}
    heads_up = len(order) == 2
    return {seat.player: ("BTN/SB" if heads_up and label == "SB" else label)
            for label, seat in order}


def stack_range(stack_bb: float | None) -> str | None:
    if stack_bb is None:
        return None
    for label, lo, hi in STACK_RANGES:
        if lo <= stack_bb < hi:
            return label
    return None


def hand_flags(hero: str, positions: dict[str, str],
               actions: list[tuple[str, str, str]]) -> dict[str, int]:
    """Flags de oportunidade/ação de UMA mão. `actions` = [(street, player,
    action)] em ordem (`ord`), só preflop/flop bastam."""
    f = dict.fromkeys(FLAG_COLUMNS, 0)
    hero_pos = positions.get(hero)

    preflop = [(p, a) for s, p, a in actions if s == "preflop" and a not in POSTS]
    flop = [(p, a) for s, p, a in actions if s == "flop"]

    n_raises = n_calls = 0
    last_raiser = opener = None
    hero_opened = hero_acted = False
    for player, action in preflop:
        if player == hero:
            if not hero_acted:
                hero_acted = True
                f["vpip_opp"] = 1
                if hero_pos in STEAL_POSITIONS and n_raises == 0 and n_calls == 0:
                    f["ats_opp"] = 1
                    f["ats"] = int(action in AGGRESSIVE)
                if (hero_pos in BLIND_POSITIONS and n_raises == 1 and n_calls == 0
                        and positions.get(opener) in STEAL_POSITIONS):
                    f["fts_opp"] = 1
                    f["fts"] = int(action == "fold")
            if n_raises == 1 and last_raiser != hero and not f["threebet_opp"]:
                f["threebet_opp"] = 1
                f["threebet"] = int(action in AGGRESSIVE)
            if hero_opened and n_raises == 2 and not f["f3b_opp"]:
                f["f3b_opp"] = 1
                f["f3b"] = int(action == "fold")
            if action in VOLUNTARY:
                f["vpip"] = 1
            if action in AGGRESSIVE:
                f["pfr"] = 1
        if action in AGGRESSIVE:
            n_raises += 1
            last_raiser = player
            if n_raises == 1:
                opener = player
                hero_opened = player == hero
        elif action == "call":
            n_calls += 1

    if last_raiser is not None and flop:
        if last_raiser == hero:
            for player, action in flop:
                if player == hero:
                    f["cbet_opp"] = 1
                    f["cbet"] = int(action in AGGRESSIVE)
                    break
                if action in AGGRESSIVE:
                    break  # alguém apostou antes: não é spot de c-bet
        else:
            faced = False
            for player, action in flop:
                if not faced:
                    if player == last_raiser:
                        if action not in AGGRESSIVE:
                            break  # agressor deu check (ou foldou): sem c-bet
                        faced = True
                    elif action in AGGRESSIVE:
                        break  # donk bet antes do agressor: não é c-bet
                elif player == hero:
                    f["fcb_opp"] = 1
                    f["fcb"] = int(action == "fold")
                    break
                elif action in AGGRESSIVE:
                    break  # raise sobre a c-bet antes do herói
    return f


def load_hand_features(conn) -> pd.DataFrame:
    """Uma linha por mão do herói, com contexto (data, torneio, buy-in,
    stack, posição recalculada) + flags de `hand_flags`. 3 queries em
    varredura ordenada pelas PKs, agrupadas em Python — sem N+1."""
    hands = conn.execute(
        """SELECT h.site, h.hand_id, h.tournament_id, h.ts, h.n_players,
                  h.button_seat, h.hero, h.hero_stack_bb, t.buyin, t.name
           FROM hands h
           LEFT JOIN tournaments t
             ON t.site = h.site AND t.tournament_id = h.tournament_id
           WHERE h.hero IS NOT NULL"""
    ).fetchall()

    seats: dict[tuple, list[Seat]] = defaultdict(list)
    for site, hand_id, seat_no, player, stack in conn.execute(
            "SELECT site, hand_id, seat_no, player, stack FROM seats"):
        seats[(site, hand_id)].append(Seat(seat_no, player, stack))

    actions: dict[tuple, list] = defaultdict(list)
    for site, hand_id, street, player, action in conn.execute(
            """SELECT site, hand_id, street, player, action FROM actions
               WHERE street IN ('preflop', 'flop')
               ORDER BY site, hand_id, ord"""):
        actions[(site, hand_id)].append((street, player, action))

    rows = []
    for site, hand_id, tid, ts, n_players, button, hero, stack_bb, buyin, name in hands:
        key = (site, hand_id)
        positions = positions_by_player(button, seats.get(key, []))
        row = {
            "site": site, "hand_id": hand_id, "tournament_id": tid,
            "tournament_name": name, "buyin": buyin, "ts": ts,
            "n_players": n_players, "stack_bb": stack_bb,
            "stack_range": stack_range(stack_bb),
            "position": positions.get(hero),
        }
        row.update(hand_flags(hero, positions, actions.get(key, [])))
        rows.append(row)

    df = pd.DataFrame(rows, columns=[
        "site", "hand_id", "tournament_id", "tournament_name", "buyin", "ts",
        "n_players", "stack_bb", "stack_range", "position", *FLAG_COLUMNS])
    df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    df[FLAG_COLUMNS] = df[FLAG_COLUMNS].astype("int64")
    return df


def data_signature(conn) -> tuple:
    """Barato (1 COUNT/MAX): muda quando mãos novas são importadas — usado
    como chave de cache pra invalidar `load_hand_features`."""
    return tuple(conn.execute("SELECT COUNT(*), MAX(ts) FROM hands").fetchone())


# ---------------- Filtros ----------------

def period_bounds(period: str, today: dt.date,
                  custom: tuple[dt.date, dt.date] | None = None) -> tuple[dt.date | None, dt.date | None]:
    """(início, fim) inclusivos. period: all | today | 7d | 30d | custom."""
    if period == "today":
        return today, today
    if period == "7d":
        return today - dt.timedelta(days=6), today
    if period == "30d":
        return today - dt.timedelta(days=29), today
    if period == "custom" and custom:
        return custom
    return None, None


def apply_filters(df: pd.DataFrame, *, start: dt.date | None = None,
                  end: dt.date | None = None, tournament: tuple[str, str] | None = None,
                  buyin: float | None = None, stack: str | None = None,
                  position: str | None = None) -> pd.DataFrame:
    """Todos os filtros combinados (AND). None = sem filtro naquela dimensão."""
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= df["ts"] >= pd.Timestamp(start)
    if end is not None:
        mask &= df["ts"] < pd.Timestamp(end + dt.timedelta(days=1))
    if tournament is not None:
        mask &= (df["site"] == tournament[0]) & (df["tournament_id"] == tournament[1])
    if buyin is not None:
        mask &= (df["buyin"] - buyin).abs() < 1e-9
    if stack is not None:
        mask &= df["stack_range"] == stack
    if position is not None:
        mask &= df["position"] == position
    return df[mask]


# ---------------- Agregações ----------------

def _pct(made: int, opps: int) -> float | None:
    return round(made / opps * 100, 1) if opps else None


def summarize(df: pd.DataFrame) -> dict:
    """{métrica: {pct, made, opps}} + hands + gap (VPIP − PFR, em p.p.)."""
    sums = df[FLAG_COLUMNS].sum()
    out = {"hands": len(df)}
    for key, (_, opp, made, _) in METRICS.items():
        o, m = int(sums[opp]), int(sums[made])
        out[key] = {"pct": _pct(m, o), "made": m, "opps": o}
    v, p = out["vpip"]["pct"], out["pfr"]["pct"]
    out["gap"] = round(v - p, 1) if v is not None and p is not None else None
    return out


def summarize_by(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Uma linha por grupo: hands, `<m>` (%), `<m>_n` (oportunidades) e gap."""
    if df.empty:
        return pd.DataFrame(columns=[*keys, "hands"])
    g = df.groupby(keys, observed=True)
    agg = g[FLAG_COLUMNS].sum()
    out = pd.DataFrame({"hands": g.size()})
    for key, (_, opp, made, _) in METRICS.items():
        o = agg[opp]
        out[key] = (agg[made] / o.where(o > 0) * 100).round(1)
        out[f"{key}_n"] = o
    out["gap"] = (out["vpip"] - out["pfr"]).round(1)
    return out.reset_index()


def long_format(by: pd.DataFrame, dim: str, metrics: list[str], min_opps: int) -> pd.DataFrame:
    """Formato longo pros gráficos, descartando pontos com amostra < min_opps."""
    rows = []
    for _, r in by.iterrows():
        for m in metrics:
            n = int(r[f"{m}_n"])
            if n < min_opps or pd.isna(r[m]):
                continue
            label, opp, made, _ = METRICS[m]
            rows.append({dim: r[dim], "métrica": label, "pct": float(r[m]),
                         "amostra": n, "feitas": round(r[m] * n / 100)})
    return pd.DataFrame(rows, columns=[dim, "métrica", "pct", "amostra", "feitas"])


def tournament_list(df: pd.DataFrame) -> pd.DataFrame:
    """Um torneio por linha (site, tournament_id, name, buyin, first_ts,
    hands), mais recente primeiro — opções do filtro de torneio."""
    if df.empty:
        return pd.DataFrame(columns=["site", "tournament_id", "name", "buyin", "first_ts", "hands"])
    return (df.groupby(["site", "tournament_id"], dropna=False)
            .agg(name=("tournament_name", "first"), buyin=("buyin", "first"),
                 first_ts=("ts", "min"), hands=("hand_id", "size"))
            .reset_index().sort_values("first_ts", ascending=False))


def evolution(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Métricas por período. freq: 'D' (dia = sessão, mesma aproximação de
    stats.sessions_by_day), 'W' (semana, início na segunda) ou 'M' (mês)."""
    d = df.dropna(subset=["ts"])
    if d.empty:
        return pd.DataFrame(columns=["period", "hands"])
    d = d.assign(period=d["ts"].dt.to_period(freq).dt.start_time)
    return summarize_by(d, ["period"])
