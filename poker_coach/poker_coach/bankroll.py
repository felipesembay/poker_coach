"""Evolução de bankroll em 3 unidades — BB, buy-ins, dinheiro — mais as
métricas derivadas (downswing, média por sessão, resultado normalizado).

Reaproveita a mesma distinção que já existe em stats.py: saldo em BB vem
100% da hand history (sempre disponível); buy-ins/dinheiro só existem
para torneios com resultado registrado (`stats.HAS_RESULT`).

Unidade `cash` (caixa) é diferente das outras: é o fluxo de dinheiro real
da conta (ver `stats.CASH_COST`/`stats.CASH_PRIZE`) — conta todo torneio
jogado (buy-in pago mesmo sem resultado lançado), desconta re-buys, e
ignora tickets (entrada paga com ticket não sai do caixa; prêmio em ticket
não entra). É a que deve bater com o saldo do site, a menos de depósitos
e saques (que não temos).

Granularidade: um ponto por dia, igual a `stats.net_bb_by_day()` — o
mesmo dia é tratado como "sessão" em todo o resto do projeto
(`stats.sessions_by_day()` já agrega por dia). Não existe uma tabela de
sessão real (ver auditoria); day = sessão aqui é a mesma aproximação já
usada no Dashboard.

Buy-ins: cada torneio contribui `(prize - buyin) / buyin` — a razão se
autonormaliza por torneio, então somar através de limites/moedas
diferentes não mistura valores incorretamente (prize e buyin de um
mesmo torneio estão sempre na mesma moeda). Dinheiro: soma bruta em $,
por isso pode ser filtrada por moeda quando há mais de uma no histórico
(sem tabela de câmbio, não há conversão automática — ver
`distinct_currencies`).
"""
from __future__ import annotations

from . import stats
from .stats import CASH_COST, CASH_PRIZE, HAS_RESULT, TOTAL_COST

MIN_TOURNAMENTS_FOR_NORM = 30
MIN_HANDS_FOR_NORM = 500


def distinct_currencies(conn) -> list[dict]:
    """Moedas presentes nos torneios com resultado, com contagem — usado
    pelo frontend para decidir se precisa pedir um filtro de moeda antes
    de mostrar o modo Dinheiro (sem isso, dá pra somar USD com BRL sem
    querer)."""
    rows = conn.execute(
        "SELECT currency, COUNT(*) FROM tournaments "
        f"WHERE currency IS NOT NULL AND {HAS_RESULT} "
        "GROUP BY currency ORDER BY COUNT(*) DESC"
    ).fetchall()
    return [{"currency": c, "tournaments": n} for c, n in rows]


def _series_bb(conn) -> list[dict]:
    rows = stats.net_bb_by_day(conn)
    cum = 0.0
    out = []
    for r in rows:
        cum += r["net_bb"]
        out.append({"period": r["date"], "value": r["net_bb"],
                     "cumulative": round(cum, 1), "n": r["hands"]})
    return out


def _series_money(conn, currency: str | None, cash: bool = False) -> list[dict]:
    """`cash=False`: resultado (só torneios com resultado, ticket pelo valor
    de face). `cash=True`: fluxo de caixa real (todos os torneios)."""
    where = "first_seen IS NOT NULL" if cash else f"{HAS_RESULT} AND first_seen IS NOT NULL"
    delta = f"{CASH_PRIZE} - {CASH_COST}" if cash else f"COALESCE(prize, 0) - {TOTAL_COST}"
    params: list = []
    if currency:
        where += " AND currency = ?"
        params.append(currency)
    rows = conn.execute(
        f"""SELECT to_char(first_seen::timestamp, 'YYYY-MM-DD') AS day,
                   SUM({delta}) AS profit, COUNT(*) AS n
            FROM tournaments WHERE {where} GROUP BY day ORDER BY day""",
        params,
    ).fetchall()
    cum = 0.0
    out = []
    for day, profit, n in rows:
        cum += profit or 0
        out.append({"period": day, "value": round(profit or 0, 2),
                     "cumulative": round(cum, 2), "n": n})
    return out


def _series_buyins(conn) -> list[dict]:
    """Cada torneio: (prize-buyin)/buyin. Somado por dia — a razão já é
    autonormalizada por torneio, então torneios de limites/moedas
    diferentes no mesmo dia se somam sem distorcer a escala."""
    rows = conn.execute(
        f"""SELECT to_char(first_seen::timestamp, 'YYYY-MM-DD') AS day,
                   SUM((COALESCE(prize, 0) - {TOTAL_COST}) / buyin) AS buyins, COUNT(*) AS n
            FROM tournaments
            WHERE {HAS_RESULT} AND first_seen IS NOT NULL AND buyin > 0
            GROUP BY day ORDER BY day"""
    ).fetchall()
    cum = 0.0
    out = []
    for day, val, n in rows:
        cum += val or 0
        out.append({"period": day, "value": round(val or 0, 3),
                     "cumulative": round(cum, 3), "n": n})
    return out


def bankroll_series(conn, unit: str = "bb", currency: str | None = None) -> list[dict]:
    """`unit`: 'bb' | 'money' | 'buyins' | 'cash'. `currency`: só usado em
    'money'/'cash' (ignorado nos outros — BB não tem moeda, buy-ins se autonormaliza).
    Retorna [{period, value, cumulative, n}] em ordem cronológica; `value`
    é o resultado daquele dia (delta), `cumulative` a soma corrida —
    o frontend escolhe qual plotar (por sessão vs. acumulado)."""
    if unit == "bb":
        return _series_bb(conn)
    if unit == "money":
        return _series_money(conn, currency)
    if unit == "buyins":
        return _series_buyins(conn)
    if unit == "cash":
        return _series_money(conn, currency, cash=True)
    raise ValueError(f"unidade desconhecida: {unit}")


def downswing(conn, unit: str = "bb", currency: str | None = None) -> dict | None:
    """Maior drawdown (pico -> vale) da série acumulada, na unidade
    pedida. None se não há série suficiente (< 2 pontos) pra definir
    um downswing."""
    series = bankroll_series(conn, unit, currency)
    if len(series) < 2:
        return None
    peak_val = series[0]["cumulative"]
    peak_period = series[0]["period"]
    best = {"value": 0.0, "start": peak_period, "trough": peak_period}
    for r in series:
        if r["cumulative"] > peak_val:
            peak_val = r["cumulative"]
            peak_period = r["period"]
        dd = peak_val - r["cumulative"]
        if dd > best["value"]:
            best = {"value": round(dd, 2), "start": peak_period, "trough": r["period"]}
    if best["value"] <= 0:
        return {"unit": unit, "value": 0.0, "start": None, "trough": None, "recovery": None}

    # recuperação: primeiro período depois do vale em que o acumulado
    # volta a alcançar o valor do pico que originou esse downswing.
    peak_val_at_start = next(r["cumulative"] for r in series if r["period"] == best["start"])
    recovery = None
    past_trough = False
    for r in series:
        if r["period"] == best["trough"]:
            past_trough = True
            continue
        if past_trough and r["cumulative"] >= peak_val_at_start:
            recovery = r["period"]
            break
    return {"unit": unit, "value": best["value"], "start": best["start"],
            "trough": best["trough"], "recovery": recovery}


def session_average(conn, unit: str = "bb", currency: str | None = None) -> dict:
    """Média por sessão (dia). Em BB, toda sessão entra (sempre
    calculável a partir da hand history). Em dinheiro/buy-ins, só
    sessões com pelo menos um torneio com resultado registrado contam —
    as demais são EXCLUÍDAS da média, não tratadas como zero."""
    n_total_sessions = len({r["date"] for r in stats.sessions_by_day(conn)})
    series = bankroll_series(conn, unit, currency)
    if not series:
        return {"unit": unit, "avg": None, "n_sessions": 0,
                "n_excluded": n_total_sessions}
    avg = sum(r["value"] for r in series) / len(series)
    n_excluded = n_total_sessions - len(series) if unit != "bb" else 0
    return {"unit": unit, "avg": round(avg, 3), "n_sessions": len(series),
             "n_excluded": max(n_excluded, 0)}


def _buyins_total_and_count(conn) -> tuple[float, int]:
    rows = conn.execute(
        f"SELECT COALESCE(prize, 0) - {TOTAL_COST} + buyin, buyin FROM tournaments "
        f"WHERE {HAS_RESULT} AND buyin > 0"
    ).fetchall()
    total = sum((prize - buyin) / buyin for prize, buyin in rows)
    return total, len(rows)


def normalized_result(conn, basis: str = "per_100_tournaments", unit: str = "bb") -> dict:
    """`basis`: 'per_100_tournaments' | 'per_1000_hands'.

    per_100_tournaments = (resultado total na unidade / nº torneios) * 100,
    exige >= MIN_TOURNAMENTS_FOR_NORM torneios com resultado (bb usa todos
    os torneios importados, não exige resultado).
    per_1000_hands = (saldo total em BB / nº mãos) * 1000, só faz sentido
    em BB (não em $/buy-ins, que são por torneio, não por mão) — exige
    >= MIN_HANDS_FOR_NORM mãos.
    Abaixo do mínimo: value=None, insufficient=True (nunca inventa valor
    com amostra pequena demais pra ser confiável)."""
    if basis == "per_1000_hands":
        if unit != "bb":
            return {"basis": basis, "unit": unit, "value": None, "n": 0,
                    "min_required": MIN_HANDS_FOR_NORM, "insufficient": True,
                    "reason": "Só disponível para a unidade BB (é uma métrica por mão)."}
        ov = stats.overview(conn)
        n = ov["hands"]
        if n < MIN_HANDS_FOR_NORM:
            return {"basis": basis, "unit": unit, "value": None, "n": n,
                    "min_required": MIN_HANDS_FOR_NORM, "insufficient": True}
        return {"basis": basis, "unit": unit, "value": round(ov["net_bb"] / n * 1000, 1),
                "n": n, "min_required": MIN_HANDS_FOR_NORM, "insufficient": False}

    if basis == "per_100_tournaments":
        if unit == "bb":
            ov = stats.overview(conn)
            n = ov["tournaments"]
            if n < MIN_TOURNAMENTS_FOR_NORM:
                return {"basis": basis, "unit": unit, "value": None, "n": n,
                        "min_required": MIN_TOURNAMENTS_FOR_NORM, "insufficient": True}
            return {"basis": basis, "unit": unit, "value": round(ov["net_bb"] / n * 100, 1),
                    "n": n, "min_required": MIN_TOURNAMENTS_FOR_NORM, "insufficient": False}
        if unit == "money":
            r = stats.roi(conn)
            n = r["tournaments"] if r else 0
            if n < MIN_TOURNAMENTS_FOR_NORM:
                return {"basis": basis, "unit": unit, "value": None, "n": n,
                        "min_required": MIN_TOURNAMENTS_FOR_NORM, "insufficient": True}
            return {"basis": basis, "unit": unit, "value": round(r["profit"] / n * 100, 2),
                    "n": n, "min_required": MIN_TOURNAMENTS_FOR_NORM, "insufficient": False}
        if unit == "cash":
            c = cash_summary(conn)
            n = c["tournaments"]
            if n < MIN_TOURNAMENTS_FOR_NORM:
                return {"basis": basis, "unit": unit, "value": None, "n": n,
                        "min_required": MIN_TOURNAMENTS_FOR_NORM, "insufficient": True}
            return {"basis": basis, "unit": unit, "value": round(c["cash_profit"] / n * 100, 2),
                    "n": n, "min_required": MIN_TOURNAMENTS_FOR_NORM, "insufficient": False}
        if unit == "buyins":
            total, n = _buyins_total_and_count(conn)
            if n < MIN_TOURNAMENTS_FOR_NORM:
                return {"basis": basis, "unit": unit, "value": None, "n": n,
                        "min_required": MIN_TOURNAMENTS_FOR_NORM, "insufficient": True}
            return {"basis": basis, "unit": unit, "value": round(total / n * 100, 2),
                    "n": n, "min_required": MIN_TOURNAMENTS_FOR_NORM, "insufficient": False}
    raise ValueError(f"basis desconhecida: {basis}")


def cash_summary(conn) -> dict:
    """Bankroll em caixa decomposto — o "extrato" que explica o número:
    quanto saiu em buy-ins/re-buys, quanto entrou em prêmios em dinheiro,
    quanto circulou em tickets (sem afetar o caixa) e quantos torneios
    ainda não têm resultado lançado (buy-in contado, prêmio 0)."""
    (n, cash_out, cash_in, buyin_cash, rebuy_n, rebuy_cost, ticket_entries,
     ticket_entries_value, ticket_entries_linked, pending_n, pending_buyin) = conn.execute(
        f"""SELECT COUNT(*),
                   COALESCE(SUM({CASH_COST}), 0),
                   COALESCE(SUM({CASH_PRIZE}), 0),
                   COALESCE(SUM(CASE WHEN entry_type = 'ticket' THEN 0 ELSE COALESCE(buyin, 0) END), 0),
                   COALESCE(SUM(COALESCE(rebuys, 0)), 0),
                   COALESCE(SUM(COALESCE(buyin, 0) * COALESCE(rebuys, 0)), 0),
                   COALESCE(SUM(CASE WHEN entry_type = 'ticket' THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN entry_type = 'ticket' THEN COALESCE(buyin, 0) ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN entry_ticket_tournament_id IS NOT NULL THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN NOT {HAS_RESULT} THEN 1 ELSE 0 END), 0),
                   COALESCE(SUM(CASE WHEN NOT {HAS_RESULT} AND COALESCE(entry_type, 'cash') <> 'ticket'
                                     THEN COALESCE(buyin, 0) ELSE 0 END), 0)
            FROM tournaments"""
    ).fetchone()
    tickets = conn.execute(
        """SELECT COUNT(*), COALESCE(SUM(t.prize), 0),
                  COALESCE(SUM(CASE WHEN u.tournament_id IS NULL THEN 1 ELSE 0 END), 0),
                  COALESCE(SUM(CASE WHEN u.tournament_id IS NULL THEN t.prize ELSE 0 END), 0)
           FROM tournaments t
           LEFT JOIN tournaments u
             ON u.entry_ticket_site = t.site AND u.entry_ticket_tournament_id = t.tournament_id
           WHERE t.prize_type = 'ticket' AND t.prize > 0"""
    ).fetchone()
    tickets_won, tickets_won_value, tickets_unlinked, tickets_unlinked_value = tickets
    r2 = lambda v: round(float(v), 2)  # noqa: E731
    return {
        "cash_profit": r2(cash_in - cash_out),
        "cash_in": r2(cash_in),
        "cash_out": r2(cash_out),
        "buyins_cash": r2(buyin_cash),
        "rebuys": int(rebuy_n),
        "rebuys_cost": r2(rebuy_cost),
        "tournaments": int(n),
        "pending_results": int(pending_n),
        "pending_buyins": r2(pending_buyin),
        "ticket_entries": int(ticket_entries),
        "ticket_entries_value": r2(ticket_entries_value),
        "ticket_entries_linked": int(ticket_entries_linked),
        "tickets_won": int(tickets_won),
        "tickets_won_value": r2(tickets_won_value),
        "tickets_unlinked": int(tickets_unlinked),
        "tickets_unlinked_value": r2(tickets_unlinked_value),
    }
