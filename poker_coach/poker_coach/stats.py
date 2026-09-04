"""Relatórios do Poker Coach.

Inclui o primeiro "detector de leak" simples: frequência de fold
preflop com stack curto (8–20 BB) por posição — exatamente o leak do
seu mockup ("excesso de folds entre 12 e 18 BB no BTN e SB").
A classificação correta de push/fold vem do motor de Nash
(poker_coach.pushfold); aqui medimos o comportamento bruto.

IMPORTANTE sobre lucro em $: ROI/ITM/ABI/lucro em dinheiro só existem
para torneios com resultado registrado (`cli.py result` ou a página de
Configuração no dashboard) — a hand history sozinha não diz sua posição
final nem o prêmio. Enquanto isso, os "dashboards de evolução" usam o
saldo em BB (fichas), que é 100% derivado das mãos importadas.
"""
import datetime as dt
import sqlite3


def overview(conn: sqlite3.Connection) -> dict:
    hands, = conn.execute("SELECT COUNT(*) FROM hands").fetchone()
    trnys, = conn.execute("SELECT COUNT(*) FROM tournaments").fetchone()
    vpip, pfr = conn.execute(
        # cast pra float: AVG(integer) no Postgres retorna NUMERIC (Decimal),
        # que quebra ao misturar com float mais adiante — SQLite não tinha
        # essa distinção de tipo.
        "SELECT AVG(hero_vpip::float)*100, AVG(hero_pfr::float)*100 FROM hands"
    ).fetchone()
    net_bb, = conn.execute(
        "SELECT SUM(CAST(hero_net_chips AS REAL)/bb) FROM hands WHERE bb > 0"
    ).fetchone()
    return {
        "hands": hands,
        "tournaments": trnys,
        "vpip_pct": round(vpip or 0, 1),
        "pfr_pct": round(pfr or 0, 1),
        "net_bb": round(net_bb or 0, 1),
    }


def roi(conn: sqlite3.Connection) -> dict | None:
    """ROI/ITM com base nos resultados registrados (cmd 'result')."""
    row = conn.execute(
        """SELECT COUNT(*), SUM(buyin), SUM(COALESCE(prize, 0)),
                  SUM(CASE WHEN prize > 0 THEN 1 ELSE 0 END),
                  AVG(buyin)
           FROM tournaments WHERE finish_position IS NOT NULL"""
    ).fetchone()
    n, invested, won, itm, abi = row
    if not n or not invested:
        return None
    return {
        "tournaments": n,
        "invested": round(invested, 2),
        "won": round(won, 2),
        "profit": round(won - invested, 2),
        "roi_pct": round((won - invested) / invested * 100, 1),
        "itm_pct": round(itm / n * 100, 1),
        "abi": round(abi, 2),
    }


def per_tournament(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        """SELECT t.site, t.tournament_id, t.buyin,
                  COUNT(h.hand_id) AS hands,
                  MIN(h.ts), MAX(h.ts),
                  t.finish_position, t.prize
           FROM tournaments t
           LEFT JOIN hands h ON h.site = t.site AND h.tournament_id = t.tournament_id
           GROUP BY t.site, t.tournament_id
           ORDER BY MIN(h.ts)"""
    ).fetchall()


def shortstack_fold_report(conn: sqlite3.Connection,
                           bb_min: float = 8, bb_max: float = 20) -> list[dict]:
    """Por posição: com que frequência o herói foldou preflop quando
    tinha entre bb_min e bb_max BB e ninguém havia limpado/apostado
    acima do BB antes dele (spot de open-shove/steal em potencial).
    """
    rows = conn.execute(
        """SELECT h.hand_id, h.site, h.hero_position, h.hero_stack_bb
           FROM hands h
           WHERE h.hero_stack_bb BETWEEN ? AND ?
             AND h.hero_position IS NOT NULL""",
        (bb_min, bb_max),
    ).fetchall()

    agg: dict[str, dict] = {}
    for hand_id, site, pos, _bb in rows:
        acts = conn.execute(
            """SELECT player, action, amount, all_in FROM actions
               WHERE site=? AND hand_id=? AND street='preflop'
               ORDER BY ord""",
            (site, hand_id),
        ).fetchall()
        hero = conn.execute(
            "SELECT hero, bb FROM hands WHERE site=? AND hand_id=?",
            (site, hand_id),
        ).fetchone()
        if not hero:
            continue
        hero_name, bb = hero

        unopened = True
        hero_action = None
        hero_all_in = False
        for player, action, amount, all_in in acts:
            if action in ("post_sb", "post_bb", "post_ante"):
                continue
            if player == hero_name:
                hero_action = action
                hero_all_in = bool(all_in)
                break
            if action in ("raise", "bet", "allin", "call"):
                unopened = False  # pote já aberto, mas seguimos até o herói agir
        if hero_action is None:
            continue

        a = agg.setdefault(pos, {"spots": 0, "folds": 0, "shoves": 0,
                                 "raises": 0, "unopened_spots": 0,
                                 "unopened_folds": 0})
        a["spots"] += 1
        # "shove" = qualquer ação do herói que o deixa all-in (raise-shove,
        # call-shove ou o marcador explícito "allin"), não só o action=="allin".
        if hero_action == "fold":
            a["folds"] += 1
        elif hero_action == "allin" or hero_all_in:
            a["shoves"] += 1
        elif hero_action == "raise":
            a["raises"] += 1
        if unopened:
            a["unopened_spots"] += 1
            if hero_action == "fold":
                a["unopened_folds"] += 1

    out = []
    for pos, a in sorted(agg.items(), key=lambda kv: -kv[1]["spots"]):
        out.append({
            "position": pos,
            "spots": a["spots"],
            "fold_pct": round(a["folds"] / a["spots"] * 100, 1),
            "shove_pct": round(a["shoves"] / a["spots"] * 100, 1),
            "raise_pct": round(a["raises"] / a["spots"] * 100, 1),
            "unopened_fold_pct": (
                round(a["unopened_folds"] / a["unopened_spots"] * 100, 1)
                if a["unopened_spots"] else None),
        })
    return out


def _parse_ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def hours_played(conn: sqlite3.Connection) -> float:
    """Soma, por torneio, (última mão - primeira mão); aproximação
    honesta (não conta tempo parado entre torneios) mas é o que dá pra
    extrair só da hand history, sem log de sessão explícito."""
    rows = conn.execute(
        "SELECT MIN(ts), MAX(ts) FROM hands WHERE ts IS NOT NULL GROUP BY tournament_id, site"
    ).fetchall()
    total = dt.timedelta()
    for lo, hi in rows:
        a, b = _parse_ts(lo), _parse_ts(hi)
        if a and b and b > a:
            total += b - a
    return round(total.total_seconds() / 3600, 1)


def satellite_history(conn: sqlite3.Connection, wins_only: bool = False) -> list[dict]:
    """Torneios marcados como tipo 'ticket' (satélites — Sharkscope não
    distingue isso do resto). Por padrão traz TODAS as tentativas,
    incluindo as que não converteram (prize=0) — não é só "vitórias",
    é o histórico de satélite. `wins_only=True` filtra só as que
    renderam ticket de fato."""
    where = "prize_type = 'ticket'" + (" AND prize > 0" if wins_only else "")
    rows = conn.execute(
        f"""SELECT site, tournament_id, name, buyin, finish_position, prize,
                   prize_note, first_seen
            FROM tournaments WHERE {where}
            ORDER BY first_seen DESC"""
    ).fetchall()
    return [{
        "torneio": name or tid, "site": s, "buyin": b,
        "converteu": "sim" if v and v > 0 else "não",
        "valor_estimado": v, "nota": note or "", "data": ts,
    } for s, tid, name, b, _p, v, note, ts in rows]


def satellite_conversion_rate(conn: sqlite3.Connection) -> dict:
    all_sat = satellite_history(conn)
    wins = [r for r in all_sat if r["converteu"] == "sim"]
    return {
        "attempts": len(all_sat), "converted": len(wins),
        "pct": round(len(wins) / len(all_sat) * 100, 1) if all_sat else None,
    }


def cash_vs_ticket_summary(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """SELECT prize_type, COUNT(*), SUM(COALESCE(prize, 0))
           FROM tournaments WHERE finish_position IS NOT NULL AND prize > 0
           GROUP BY prize_type"""
    ).fetchall()
    out = {"cash": {"count": 0, "total": 0.0}, "ticket": {"count": 0, "total": 0.0}}
    for ptype, n, total in row:
        key = ptype if ptype in out else "cash"  # resultados antigos (sem tipo) contam como cash
        out[key] = {"count": n, "total": round(total or 0, 2)}
    return out


def results_pending(conn: sqlite3.Connection) -> list[tuple]:
    """Torneios já importados sem resultado registrado ainda — pra
    popular o formulário de 'registrar resultado' na Configuração."""
    return conn.execute(
        """SELECT t.site, t.tournament_id, t.buyin, t.currency,
                  COUNT(h.hand_id) AS hands, MIN(h.ts) AS first_seen
           FROM tournaments t
           LEFT JOIN hands h ON h.site = t.site AND h.tournament_id = t.tournament_id
           WHERE t.finish_position IS NULL
           GROUP BY t.site, t.tournament_id
           ORDER BY first_seen DESC"""
    ).fetchall()


def position_stats(conn: sqlite3.Connection) -> list[dict]:
    """VPIP/PFR/saldo em BB por posição — disponível sem nenhum
    resultado registrado (é tudo derivado da hand history)."""
    rows = conn.execute(
        """SELECT hero_position,
                  COUNT(*) AS spots,
                  AVG(hero_vpip::float) * 100 AS vpip_pct,
                  AVG(hero_pfr::float) * 100 AS pfr_pct,
                  SUM(CAST(hero_net_chips AS REAL) / bb) AS net_bb
           FROM hands
           WHERE hero_position IS NOT NULL AND bb > 0
           GROUP BY hero_position"""
    ).fetchall()
    order = {p: i for i, p in enumerate(
        ["UTG", "UTG+1", "UTG+2", "MP", "MP+1", "HJ", "CO", "BTN", "SB", "BB"])}
    out = [{
        "position": pos, "spots": spots,
        "vpip_pct": round(vpip or 0, 1), "pfr_pct": round(pfr or 0, 1),
        "net_bb": round(net_bb or 0, 1),
    } for pos, spots, vpip, pfr, net_bb in rows]
    out.sort(key=lambda r: order.get(r["position"], 99))
    return out


STACK_BUCKETS = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (30, 50)]


def stack_bucket_stats(conn: sqlite3.Connection,
                        buckets: list[tuple[float, float]] = STACK_BUCKETS) -> list[dict]:
    """Por faixa de stack efetivo (hero_stack_bb no início da mão): spots,
    fold/push/call % no preflop e saldo em BB — a tabela "0-5BB / 5-10BB /
    ..." pedida no dashboard de Stack."""
    out = []
    for lo, hi in buckets:
        row = conn.execute(
            """SELECT COUNT(*), SUM(CAST(hero_net_chips AS REAL) / bb)
               FROM hands WHERE hero_stack_bb >= ? AND hero_stack_bb < ? AND bb > 0""",
            (lo, hi),
        ).fetchone()
        spots, net_bb = row
        if not spots:
            out.append({"bucket": f"{lo:g}-{hi:g}BB", "spots": 0, "fold_pct": None,
                        "push_pct": None, "call_pct": None, "net_bb": 0.0})
            continue
        hand_ids = conn.execute(
            """SELECT site, hand_id, hero FROM hands
               WHERE hero_stack_bb >= ? AND hero_stack_bb < ? AND bb > 0""",
            (lo, hi),
        ).fetchall()
        folds = pushes = calls = counted = 0
        for site, hand_id, hero in hand_ids:
            first = conn.execute(
                """SELECT action, all_in FROM actions
                   WHERE site=? AND hand_id=? AND street='preflop' AND player=?
                     AND action NOT IN ('post_sb','post_bb','post_ante')
                   ORDER BY ord LIMIT 1""",
                (site, hand_id, hero),
            ).fetchone()
            if not first:
                continue
            action, all_in = first
            counted += 1
            if action == "fold":
                folds += 1
            elif action in ("raise", "allin") or all_in:
                pushes += 1
            elif action == "call":
                calls += 1
        out.append({
            "bucket": f"{lo:g}-{hi:g}BB", "spots": spots,
            "fold_pct": round(folds / counted * 100, 1) if counted else None,
            "push_pct": round(pushes / counted * 100, 1) if counted else None,
            "call_pct": round(calls / counted * 100, 1) if counted else None,
            "net_bb": round(net_bb or 0, 1),
        })
    return out


def profit_by_period(conn: sqlite3.Connection, period: str = "day") -> list[dict]:
    """Lucro em $ por dia/semana/mês, só pros torneios COM resultado
    registrado (sem isso não há como saber o prêmio). period: 'day' |
    'week' | 'month'.

    Semana = semana ISO (segunda-feira, 'IYYY-"W"IW' -> ex. '2026-W32'),
    não a numeração %W do SQLite (domingo-início) — combina com
    `date.isocalendar()` do Python, usado em app_pages/home.py pra achar
    a semana atual nesse mesmo formato."""
    fmt = {"day": "YYYY-MM-DD", "week": 'IYYY-"W"IW', "month": "YYYY-MM"}[period]
    rows = conn.execute(
        f"""SELECT to_char(first_seen::timestamp, '{fmt}') AS bucket,
                   SUM(COALESCE(prize, 0) - buyin) AS profit,
                   COUNT(*) AS tournaments
            FROM tournaments
            WHERE finish_position IS NOT NULL AND first_seen IS NOT NULL
            GROUP BY bucket ORDER BY bucket"""
    ).fetchall()
    return [{"period": b, "profit": round(p or 0, 2), "tournaments": n} for b, p, n in rows]


def net_bb_by_hour(conn: sqlite3.Connection) -> list[dict]:
    """Saldo em BB por hora do dia (0-23) — disponível sem resultado
    registrado, e é o dado por trás de 'você joga melhor às 19h do que
    à meia-noite'."""
    rows = conn.execute(
        """SELECT EXTRACT(HOUR FROM ts::timestamp)::int AS hour,
                  SUM(CAST(hero_net_chips AS REAL) / bb) AS net_bb,
                  COUNT(*) AS hands
           FROM hands WHERE ts IS NOT NULL AND bb > 0
           GROUP BY hour ORDER BY hour"""
    ).fetchall()
    return [{"hour": h, "net_bb": round(n or 0, 1), "hands": c} for h, n, c in rows]


def net_bb_by_weekday(conn: sqlite3.Connection) -> list[dict]:
    """Saldo em BB por dia da semana (0=domingo..6=sábado — EXTRACT(DOW)
    do Postgres usa a mesma convenção que o antigo strftime %w do SQLite)."""
    names = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
    rows = conn.execute(
        """SELECT EXTRACT(DOW FROM ts::timestamp)::int AS wd,
                  SUM(CAST(hero_net_chips AS REAL) / bb) AS net_bb,
                  COUNT(*) AS hands
           FROM hands WHERE ts IS NOT NULL AND bb > 0
           GROUP BY wd ORDER BY wd"""
    ).fetchall()
    return [{"weekday": names[wd], "net_bb": round(n or 0, 1), "hands": c} for wd, n, c in rows]


def profit_by_buyin(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT buyin, COUNT(*), SUM(buyin), SUM(COALESCE(prize, 0)),
                  SUM(CASE WHEN prize > 0 THEN 1 ELSE 0 END)
           FROM tournaments WHERE finish_position IS NOT NULL
           GROUP BY buyin ORDER BY buyin"""
    ).fetchall()
    out = []
    for buyin, n, invested, won, itm in rows:
        profit = (won or 0) - (invested or 0)
        out.append({
            "buyin": buyin, "tournaments": n,
            "profit": round(profit, 2),
            "roi_pct": round(profit / invested * 100, 1) if invested else None,
            "itm_pct": round(itm / n * 100, 1) if n else None,
        })
    return out
