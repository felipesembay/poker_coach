"""Camada de persistência (PostgreSQL, via psycopg2).

`PGConnection` é um wrapper fino sobre a conexão psycopg2 que expõe a
MESMA interface que o resto do código já usa desde a Fase 1 em SQLite
(`conn.execute(sql, params)` retornando um cursor, parâmetros com `?`
em vez de `%s`) — assim stats.py/replay.py/pushfold/analyze.py/
icm_analyze.py/app_pages/*.py não precisaram ser reescritos call-site
por call-site, só a camada de conexão mudou de driver.

Diferença de comportamento importante que EXIGIU mudança de lógica (não
só de driver): SQLite não aborta a transação inteira quando um INSERT
falha por PK duplicada — Postgres aborta (qualquer comando seguinte na
mesma transação falha com "current transaction is aborted" até um
ROLLBACK). Por isso o padrão antigo de "tenta INSERT, pega
IntegrityError, retorna False" foi trocado por `ON CONFLICT ... DO
NOTHING` + checar `cursor.rowcount` — nunca levanta exceção pro caso
esperado de "mão já importada", então nunca aborta a transação do
import incremental.
"""
import json
import re

import psycopg2
import psycopg2.extras

from .models import Hand

_QMARK = re.compile(r"\?")


def _pg(sql: str) -> str:
    return _QMARK.sub("%s", sql)


class PGConnection:
    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn)

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        cur.execute(_pg(sql), params if params else None)
        return cur

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor()
        seq = list(seq_of_params)
        if seq:
            cur.executemany(_pg(sql), seq)
        return cur

    def executescript(self, sql: str) -> None:
        """DDL puro (sem `?`), várias instruções separadas por `;` —
        psycopg2 aceita isso num único execute()."""
        cur = self._conn.cursor()
        cur.execute(sql)
        cur.close()

    def cursor(self):
        return self._conn.cursor()

    @property
    def raw(self):
        """Conexão psycopg2 crua — usar quando algo externo (ex.:
        pandas.read_sql_query) precisa reconhecer explicitamente uma
        conexão DBAPI2 padrão em vez do wrapper."""
        return self._conn

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        # fallback pra qualquer coisa que pandas.read_sql_query ou
        # outro código externo espere de uma conexão DBAPI2 de verdade.
        return getattr(self._conn, name)


SCHEMA = """
CREATE TABLE IF NOT EXISTS tournaments (
    site TEXT NOT NULL,
    tournament_id TEXT NOT NULL,
    buyin REAL,
    currency TEXT,
    first_seen TEXT,
    last_seen TEXT,
    finish_position INTEGER,
    prize REAL,
    prize_type TEXT,
    prize_note TEXT,
    name TEXT,
    rebuys INTEGER DEFAULT 0,
    entry_type TEXT,                  -- 'cash' | 'ticket' (NULL = cash)
    entry_ticket_site TEXT,           -- torneio onde o ticket de entrada foi ganho
    entry_ticket_tournament_id TEXT,
    PRIMARY KEY (site, tournament_id)
);

CREATE TABLE IF NOT EXISTS hands (
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    tournament_id TEXT NOT NULL,
    ts TEXT,
    level INTEGER,
    sb INTEGER, bb INTEGER, ante INTEGER,
    table_name TEXT,
    max_players INTEGER,
    n_players INTEGER,
    button_seat INTEGER,
    hero TEXT,
    hero_cards TEXT,
    hero_position TEXT,
    hero_stack_chips INTEGER,
    hero_stack_bb REAL,
    hero_vpip INTEGER,
    hero_pfr INTEGER,
    hero_net_chips INTEGER,
    board TEXT,
    favorite INTEGER DEFAULT 0,
    PRIMARY KEY (site, hand_id)
);

CREATE TABLE IF NOT EXISTS actions (
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    ord INTEGER NOT NULL,
    street TEXT,
    player TEXT,
    action TEXT,
    amount INTEGER,
    all_in INTEGER,
    PRIMARY KEY (site, hand_id, ord)
);

CREATE TABLE IF NOT EXISTS seats (
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    seat_no INTEGER NOT NULL,
    player TEXT,
    stack INTEGER,
    PRIMARY KEY (site, hand_id, seat_no)
);

CREATE TABLE IF NOT EXISTS results (
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    player TEXT NOT NULL,
    net_chips INTEGER NOT NULL,
    PRIMARY KEY (site, hand_id, player)
);

CREATE TABLE IF NOT EXISTS payouts (
    site TEXT NOT NULL,
    tournament_id TEXT NOT NULL,
    place INTEGER NOT NULL,
    prize REAL NOT NULL,
    PRIMARY KEY (site, tournament_id, place)
);

CREATE TABLE IF NOT EXISTS showdowns (
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    player TEXT NOT NULL,
    cards TEXT,
    PRIMARY KEY (site, hand_id, player)
);

CREATE TABLE IF NOT EXISTS notes (
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (site, hand_id)
);

CREATE TABLE IF NOT EXISTS tags (
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (site, hand_id, tag)
);

CREATE TABLE IF NOT EXISTS quiz_log (
    id SERIAL PRIMARY KEY,
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    user_decision TEXT NOT NULL,
    nash_decision TEXT NOT NULL,
    correct INTEGER NOT NULL,
    ev_lost_bb REAL
);

CREATE TABLE IF NOT EXISTS adaptive_trainer_log (
    id SERIAL PRIMARY KEY,
    ts TEXT NOT NULL,
    source TEXT NOT NULL,       -- "historical" | "synthetic"
    site TEXT,                  -- só preenchido quando source="historical"
    hand_id TEXT,
    position TEXT,
    hero_cards TEXT NOT NULL,
    effective_bb REAL NOT NULL,
    pot_bb REAL NOT NULL,
    user_action TEXT NOT NULL,
    personal_policy_action TEXT,    -- argmax da Personal Policy (Fase 2), se carregada
    reference_action TEXT NOT NULL, -- Nash (motor existente)
    ev_user_bb REAL NOT NULL,
    ev_reference_bb REAL NOT NULL,
    ev_gap_bb REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_cache (
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (site, hand_id, step_order)
);

CREATE TABLE IF NOT EXISTS decision_analysis (
    site TEXT NOT NULL,
    hand_id TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    tournament_id TEXT,
    player TEXT NOT NULL,
    street TEXT NOT NULL,
    position TEXT,
    hero_cards TEXT,
    board TEXT,
    pot_before_action_bb REAL,
    bet_faced_bb REAL,
    call_cost_bb REAL,
    effective_stack_bb REAL,
    number_of_opponents INTEGER,
    context_type TEXT NOT NULL,
    model_type TEXT NOT NULL,
    hero_equity REAL,
    required_equity REAL,
    pot_odds_ratio TEXT,
    ev_call_bb REAL,
    ev_fold_bb REAL,
    ev_push_bb REAL,
    recommended_action TEXT,
    actual_action TEXT,
    actual_result_bb REAL,
    assumptions TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (site, hand_id, step_order)
);

CREATE INDEX IF NOT EXISTS idx_hands_trny ON hands(site, tournament_id);
CREATE INDEX IF NOT EXISTS idx_hands_stackbb ON hands(hero_stack_bb);
CREATE INDEX IF NOT EXISTS idx_decision_analysis_hand ON decision_analysis(site, hand_id);
CREATE INDEX IF NOT EXISTS idx_decision_analysis_model ON decision_analysis(model_type, context_type);
"""


def _migrate(conn: PGConnection) -> None:
    """CREATE TABLE IF NOT EXISTS não adiciona coluna em tabela que já
    existe de uma versão anterior do schema — checa via
    information_schema e altera manualmente. Idempotente."""
    def _cols(table):
        return {r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=?", (table,))}

    t_cols = _cols("tournaments")
    if "prize_type" not in t_cols:
        conn.execute("ALTER TABLE tournaments ADD COLUMN prize_type TEXT")
    if "prize_note" not in t_cols:
        conn.execute("ALTER TABLE tournaments ADD COLUMN prize_note TEXT")
    if "name" not in t_cols:
        conn.execute("ALTER TABLE tournaments ADD COLUMN name TEXT")
    if "rebuys" not in t_cols:
        conn.execute("ALTER TABLE tournaments ADD COLUMN rebuys INTEGER DEFAULT 0")
    if "entry_type" not in t_cols:
        conn.execute("ALTER TABLE tournaments ADD COLUMN entry_type TEXT")
    if "entry_ticket_site" not in t_cols:
        conn.execute("ALTER TABLE tournaments ADD COLUMN entry_ticket_site TEXT")
    if "entry_ticket_tournament_id" not in t_cols:
        conn.execute("ALTER TABLE tournaments ADD COLUMN entry_ticket_tournament_id TEXT")

    h_cols = _cols("hands")
    if "favorite" not in h_cols:
        conn.execute("ALTER TABLE hands ADD COLUMN favorite INTEGER DEFAULT 0")


def connect(dsn: str) -> PGConnection:
    """`dsn`: string de conexão Postgres, ex.
    'postgresql://postgres:airflow@172.17.0.3:5432/poker_coach'."""
    conn = PGConnection(dsn)
    conn.executescript(SCHEMA)
    conn.commit()
    _migrate(conn)
    conn.commit()
    return conn


def insert_hand(conn: PGConnection, h: Hand) -> bool:
    """Insere uma mão. Retorna False se já existia (import incremental).
    `ON CONFLICT DO NOTHING` + rowcount em vez de exceção — ver docstring
    do módulo (Postgres aborta a transação inteira numa exceção não
    tratada com ROLLBACK explícito, SQLite não)."""
    hs = h.hero_seat()
    cur = conn.execute(
        """INSERT INTO hands
               (site, hand_id, tournament_id, ts, level, sb, bb, ante,
                table_name, max_players, n_players, button_seat, hero,
                hero_cards, hero_position, hero_stack_chips, hero_stack_bb,
                hero_vpip, hero_pfr, hero_net_chips, board, favorite)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
           ON CONFLICT (site, hand_id) DO NOTHING""",
        (h.site, h.hand_id, h.tournament_id, h.timestamp, h.level,
         h.sb, h.bb, h.ante, h.table_name, h.max_players, h.n_players(),
         h.button_seat, h.hero, h.hero_cards, h.hero_position(),
         hs.stack if hs else None, h.hero_stack_bb(),
         int(h.hero_vpip()), int(h.hero_pfr()), h.hero_net_chips(),
         h.board),
    )
    if cur.rowcount == 0:
        return False

    conn.executemany(
        "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?) "
        "ON CONFLICT (site, hand_id, ord) DO NOTHING",
        [(h.site, h.hand_id, a.order, a.street, a.player, a.action,
          a.amount, int(a.all_in)) for a in h.actions],
    )

    conn.executemany(
        "INSERT INTO seats VALUES (?,?,?,?,?) "
        "ON CONFLICT (site, hand_id, seat_no) DO NOTHING",
        [(h.site, h.hand_id, s.seat_no, s.player, s.stack) for s in h.seats],
    )

    conn.executemany(
        "INSERT INTO showdowns VALUES (?,?,?,?) "
        "ON CONFLICT (site, hand_id, player) DO NOTHING",
        [(h.site, h.hand_id, player, cards) for player, cards in h.shown_cards.items()],
    )

    if h.results:
        conn.executemany(
            "INSERT INTO results VALUES (?,?,?,?) "
            "ON CONFLICT (site, hand_id, player) DO NOTHING",
            [(h.site, h.hand_id, player, net) for player, net in h.results.items()],
        )

    conn.execute(
        """INSERT INTO tournaments (site, tournament_id, buyin, currency, first_seen, last_seen)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(site, tournament_id) DO UPDATE SET
             buyin = COALESCE(excluded.buyin, tournaments.buyin),
             currency = COALESCE(excluded.currency, tournaments.currency),
             first_seen = LEAST(COALESCE(tournaments.first_seen, excluded.first_seen), excluded.first_seen),
             last_seen = GREATEST(COALESCE(tournaments.last_seen, excluded.last_seen), excluded.last_seen)""",
        (h.site, h.tournament_id, h.buyin, h.currency, h.timestamp, h.timestamp),
    )
    return True


def insert_hands_batch(conn: PGConnection, hands: list[Hand]) -> int:
    """Mesma semântica de `insert_hand` (idempotente, `ON CONFLICT DO
    NOTHING`), mas em lote pro arquivo inteiro — 1 `executemany` por
    tabela pra todas as mãos, em vez de até 6 round-trips ao banco POR
    MÃO num loop Python (era o gargalo confirmado do import de hand
    history). Assume que todas as mãos são do MESMO `site` — verdade
    pro caso de uso real (um arquivo de hand history é sempre de uma
    sala só, `detect_site` roda uma vez por arquivo em `imports.py`).
    Retorna quantas mãos eram novas."""
    if not hands:
        return 0

    site = hands[0].site
    hand_ids = [h.hand_id for h in hands]
    existing = {
        row[0] for row in conn.execute(
            "SELECT hand_id FROM hands WHERE site=? AND hand_id = ANY(?)",
            (site, hand_ids),
        )
    }
    new_hands = [h for h in hands if h.hand_id not in existing]
    if not new_hands:
        return 0

    conn.executemany(
        """INSERT INTO hands
               (site, hand_id, tournament_id, ts, level, sb, bb, ante,
                table_name, max_players, n_players, button_seat, hero,
                hero_cards, hero_position, hero_stack_chips, hero_stack_bb,
                hero_vpip, hero_pfr, hero_net_chips, board, favorite)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
           ON CONFLICT (site, hand_id) DO NOTHING""",
        [
            (h.site, h.hand_id, h.tournament_id, h.timestamp, h.level,
             h.sb, h.bb, h.ante, h.table_name, h.max_players, h.n_players(),
             h.button_seat, h.hero, h.hero_cards, h.hero_position(),
             (h.hero_seat().stack if h.hero_seat() else None), h.hero_stack_bb(),
             int(h.hero_vpip()), int(h.hero_pfr()), h.hero_net_chips(), h.board)
            for h in new_hands
        ],
    )

    actions = [
        (h.site, h.hand_id, a.order, a.street, a.player, a.action, a.amount, int(a.all_in))
        for h in new_hands for a in h.actions
    ]
    if actions:
        conn.executemany(
            "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT (site, hand_id, ord) DO NOTHING", actions,
        )

    seats = [
        (h.site, h.hand_id, s.seat_no, s.player, s.stack)
        for h in new_hands for s in h.seats
    ]
    if seats:
        conn.executemany(
            "INSERT INTO seats VALUES (?,?,?,?,?) "
            "ON CONFLICT (site, hand_id, seat_no) DO NOTHING", seats,
        )

    showdowns = [
        (h.site, h.hand_id, player, cards)
        for h in new_hands for player, cards in h.shown_cards.items()
    ]
    if showdowns:
        conn.executemany(
            "INSERT INTO showdowns VALUES (?,?,?,?) "
            "ON CONFLICT (site, hand_id, player) DO NOTHING", showdowns,
        )

    results = [
        (h.site, h.hand_id, player, net)
        for h in new_hands for player, net in h.results.items()
    ]
    if results:
        conn.executemany(
            "INSERT INTO results VALUES (?,?,?,?) "
            "ON CONFLICT (site, hand_id, player) DO NOTHING", results,
        )

    conn.executemany(
        """INSERT INTO tournaments (site, tournament_id, buyin, currency, first_seen, last_seen)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(site, tournament_id) DO UPDATE SET
             buyin = COALESCE(excluded.buyin, tournaments.buyin),
             currency = COALESCE(excluded.currency, tournaments.currency),
             first_seen = LEAST(COALESCE(tournaments.first_seen, excluded.first_seen), excluded.first_seen),
             last_seen = GREATEST(COALESCE(tournaments.last_seen, excluded.last_seen), excluded.last_seen)""",
        [(h.site, h.tournament_id, h.buyin, h.currency, h.timestamp, h.timestamp) for h in new_hands],
    )

    return len(new_hands)


def set_result(conn, site: str, tournament_id: str, position: int | None, prize: float | None,
                prize_type: str | None = None, prize_note: str | None = None,
                name: str | None = None, buyin: float | None = None,
                currency: str | None = None, date_iso: str | None = None):
    """Registra o resultado de um torneio. prize_type: 'cash' ou 'ticket'
    — None quando ainda não foi marcado (não presume "cash": em freeroll/
    satélite o prêmio costuma ser ticket, o que muda ROI/ITM). `prize` é o
    valor em $ real ou estimado, `prize_note` a descrição livre.

    Upsert: se o torneio já existe (normalmente porque a hand history foi
    importada), só atualiza o resultado — `name`/`buyin`/`date_iso`, se
    passados, preenchem só o que estiver vazio (COALESCE), sem sobrescrever
    o que já veio da hand history. Se o torneio NÃO existe ainda (resultado
    lançado manualmente, sem hand history correspondente — desconexão,
    bust-out antes de qualquer mão, fora do período exportado etc.), cria a
    linha do zero; nesse caso `buyin`/`date_iso` são necessários pra ter
    algum contexto temporal/financeiro."""
    conn.execute(
        """INSERT INTO tournaments
               (site, tournament_id, buyin, currency, first_seen, last_seen,
                finish_position, prize, prize_type, prize_note, name)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(site, tournament_id) DO UPDATE SET
             finish_position = excluded.finish_position,
             prize = excluded.prize,
             prize_type = excluded.prize_type,
             prize_note = excluded.prize_note,
             name = COALESCE(tournaments.name, excluded.name),
             buyin = COALESCE(tournaments.buyin, excluded.buyin),
             currency = COALESCE(tournaments.currency, excluded.currency),
             first_seen = COALESCE(tournaments.first_seen, excluded.first_seen),
             last_seen = COALESCE(tournaments.last_seen, excluded.last_seen)""",
        (site, tournament_id, buyin, currency, date_iso, date_iso,
         position, prize, prize_type, prize_note, name),
    )


# ---------------- Entrada do torneio: re-buys e tickets ----------------
#
# Nada disso vem da hand history (ela não diz se você pagou a entrada com
# ticket, nem registra re-buy de forma confiável) — é sempre lançado à mão
# na tela de Torneios. Alimenta o bankroll em caixa (stats.CASH_COST).

def set_tournament_entry(conn: PGConnection, site: str, tournament_id: str, *,
                         rebuys: int, entry_type: str,
                         ticket_site: str | None = None,
                         ticket_tournament_id: str | None = None) -> None:
    """Re-buys (quantidade, cada um custa o buy-in) + forma de entrada.
    `entry_type='ticket'` = entrada paga com ticket (não sai do caixa);
    opcionalmente vinculada ao torneio onde o ticket foi ganho. Um ticket
    só pode ser usado uma vez. Levanta ValueError em entrada inválida e
    LookupError se o torneio não existe."""
    if rebuys < 0:
        raise ValueError("rebuys não pode ser negativo")
    if entry_type not in ("cash", "ticket"):
        raise ValueError(f"entry_type inválido: {entry_type!r}")
    if (ticket_site is None) != (ticket_tournament_id is None):
        raise ValueError("vínculo de ticket exige site e tournament_id juntos")
    if ticket_tournament_id is not None:
        if entry_type != "ticket":
            raise ValueError("vínculo de ticket só vale para entrada via ticket")
        if (ticket_site, ticket_tournament_id) == (site, tournament_id):
            raise ValueError("um torneio não pode usar o próprio ticket")
        src = conn.execute(
            "SELECT prize_type, prize FROM tournaments WHERE site=? AND tournament_id=?",
            (ticket_site, ticket_tournament_id)).fetchone()
        if src is None or src[0] != "ticket" or not src[1] or src[1] <= 0:
            raise ValueError("torneio de origem não tem prêmio do tipo ticket")
        used = conn.execute(
            """SELECT tournament_id FROM tournaments
               WHERE entry_ticket_site=? AND entry_ticket_tournament_id=?
                 AND NOT (site=? AND tournament_id=?)""",
            (ticket_site, ticket_tournament_id, site, tournament_id)).fetchone()
        if used is not None:
            raise ValueError(f"esse ticket já foi usado no torneio #{used[0]}")
    cur = conn.execute(
        """UPDATE tournaments SET rebuys=?, entry_type=?,
                  entry_ticket_site=?, entry_ticket_tournament_id=?
           WHERE site=? AND tournament_id=?""",
        (rebuys, entry_type, ticket_site, ticket_tournament_id, site, tournament_id))
    if cur.rowcount == 0:
        raise LookupError(f"torneio {site}/{tournament_id} não encontrado")


def ticket_sources(conn: PGConnection) -> list[dict]:
    """Tickets ganhos (prêmio tipo ticket > 0), com o torneio em que cada
    um foi usado (None = ainda não vinculado a nenhuma entrada)."""
    rows = conn.execute(
        """SELECT t.site, t.tournament_id, t.name, t.prize, t.first_seen,
                  u.site, u.tournament_id
           FROM tournaments t
           LEFT JOIN tournaments u
             ON u.entry_ticket_site = t.site AND u.entry_ticket_tournament_id = t.tournament_id
           WHERE t.prize_type = 'ticket' AND t.prize > 0
           ORDER BY t.first_seen DESC NULLS LAST"""
    ).fetchall()
    return [{"site": s, "tournament_id": tid, "name": n, "value": v, "won_at": ts,
             "used_by_site": us, "used_by_tournament_id": ut}
            for s, tid, n, v, ts, us, ut in rows]


# ---------------- Replayer: favoritos, notas, tags ----------------

SUGGESTED_TAGS = ["Push/Fold", "ICM", "Bluff", "Hero Call", "Cooler", "Bad Beat"]


def set_favorite(conn: PGConnection, site: str, hand_id: str, favorite: bool) -> None:
    conn.execute("UPDATE hands SET favorite=? WHERE site=? AND hand_id=?",
                 (int(favorite), site, hand_id))


def set_note(conn: PGConnection, site: str, hand_id: str, text: str) -> None:
    import datetime as _dt
    if not text.strip():
        conn.execute("DELETE FROM notes WHERE site=? AND hand_id=?", (site, hand_id))
        return
    conn.execute(
        """INSERT INTO notes (site, hand_id, text, created_at) VALUES (?,?,?,?)
           ON CONFLICT(site, hand_id) DO UPDATE SET text=excluded.text, created_at=excluded.created_at""",
        (site, hand_id, text, _dt.datetime.now().isoformat(timespec="seconds")),
    )


def get_note(conn: PGConnection, site: str, hand_id: str) -> str:
    row = conn.execute("SELECT text FROM notes WHERE site=? AND hand_id=?", (site, hand_id)).fetchone()
    return row[0] if row else ""


def get_tags(conn: PGConnection, site: str, hand_id: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT tag FROM tags WHERE site=? AND hand_id=? ORDER BY tag", (site, hand_id))]


def set_tags(conn: PGConnection, site: str, hand_id: str, tags: list[str]) -> None:
    """Substitui todas as tags da mão pela lista dada (delete + insere de novo)."""
    conn.execute("DELETE FROM tags WHERE site=? AND hand_id=?", (site, hand_id))
    conn.executemany(
        "INSERT INTO tags VALUES (?,?,?) ON CONFLICT (site, hand_id, tag) DO NOTHING",
        [(site, hand_id, t) for t in tags if t.strip()])


def all_tags_used(conn: PGConnection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT DISTINCT tag FROM tags ORDER BY tag")]


# ---------------- Modo Estudo (quiz) ----------------

def log_quiz_answer(conn: PGConnection, site: str, hand_id: str,
                     user_decision: str, nash_decision: str, ev_lost_bb: float | None) -> None:
    import datetime as _dt
    conn.execute(
        "INSERT INTO quiz_log (site, hand_id, ts, user_decision, nash_decision, correct, ev_lost_bb) "
        "VALUES (?,?,?,?,?,?,?)",
        (site, hand_id, _dt.datetime.now().isoformat(timespec="seconds"),
         user_decision, nash_decision, int(user_decision == nash_decision), ev_lost_bb),
    )


def quiz_stats(conn: PGConnection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*), SUM(correct) FROM quiz_log").fetchone()
    total, correct = row
    return {
        "total": total or 0, "correct": correct or 0,
        "pct": round((correct or 0) / total * 100, 1) if total else None,
    }


# ---------------- Cache de Decision Analysis (Replayer) ----------------
#
# `decision_analysis` é write-only por propósito (alimenta agregações de
# decision_stats.py com colunas numéricas típadas) — não é lida de volta
# antes de recalcular. Essa tabela aqui É o cache de verdade: guarda a
# resposta JSON completa já montada (`DecisionAnalysisOut`), pra não
# pagar de novo o Monte Carlo ao vivo (10-16s, medido nesta sessão) toda
# vez que a mesma mão/step é revisitada no Replayer.

def get_cached_decision(conn: PGConnection, site: str, hand_id: str, step_order: int) -> str | None:
    row = conn.execute(
        "SELECT response_json FROM decision_cache WHERE site=? AND hand_id=? AND step_order=?",
        (site, hand_id, step_order),
    ).fetchone()
    return row[0] if row else None


def save_cached_decision(conn: PGConnection, site: str, hand_id: str, step_order: int,
                          response_json: str) -> None:
    import datetime as _dt
    conn.execute(
        """INSERT INTO decision_cache (site, hand_id, step_order, response_json, created_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT (site, hand_id, step_order) DO UPDATE SET
             response_json=excluded.response_json, created_at=excluded.created_at""",
        (site, hand_id, step_order, response_json, _dt.datetime.now().isoformat(timespec="seconds")),
    )


# ---------------- Adaptive Trainer (seção 19 do plano de RL) ----------------

def log_adaptive_trainer_answer(
    conn: PGConnection, *, source: str, site: str | None, hand_id: str | None,
    position: str | None, hero_cards: str, effective_bb: float, pot_bb: float,
    user_action: str, personal_policy_action: str | None, reference_action: str,
    ev_user_bb: float, ev_reference_bb: float, ev_gap_bb: float,
) -> None:
    import datetime as _dt
    conn.execute(
        """INSERT INTO adaptive_trainer_log (
               ts, source, site, hand_id, position, hero_cards, effective_bb, pot_bb,
               user_action, personal_policy_action, reference_action,
               ev_user_bb, ev_reference_bb, ev_gap_bb
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (_dt.datetime.now().isoformat(timespec="seconds"), source, site, hand_id,
         position, hero_cards, effective_bb, pot_bb, user_action, personal_policy_action,
         reference_action, ev_user_bb, ev_reference_bb, ev_gap_bb),
    )


def adaptive_trainer_stats(conn: PGConnection) -> dict:
    """Evolução ao longo do tempo (seção 19: "isso permitirá futuramente
    medir evolução") — agregado geral + por dia, igual ao padrão já usado
    em `quiz_stats`/`stats.pushfold_training_by_day`."""
    row = conn.execute(
        "SELECT COUNT(*), SUM((user_action = reference_action)::int), AVG(ev_gap_bb) "
        "FROM adaptive_trainer_log"
    ).fetchone()
    total, correct, avg_gap = row
    by_day = conn.execute(
        "SELECT ts::date AS day, COUNT(*), "
        "SUM((user_action = reference_action)::int), AVG(ev_gap_bb) "
        "FROM adaptive_trainer_log GROUP BY day ORDER BY day"
    ).fetchall()
    return {
        "total": total or 0, "correct": correct or 0,
        "pct": round((correct or 0) / total * 100, 1) if total else None,
        "avg_ev_gap_bb": round(avg_gap, 3) if avg_gap is not None else None,
        "by_day": [
            {"day": str(day), "n": n, "correct": c, "avg_ev_gap_bb": round(g, 3) if g is not None else None}
            for day, n, c, g in by_day
        ],
    }


# ---------------- Estrutura de premiação (ICM) ----------------

def set_payouts(conn: PGConnection, site: str, tournament_id: str,
                 prizes: list[float]) -> None:
    """`prizes` = [1º lugar, 2º, 3º, ...] em $. Substitui a estrutura
    inteira do torneio (delete + insere de novo)."""
    conn.execute("DELETE FROM payouts WHERE site=? AND tournament_id=?", (site, tournament_id))
    conn.executemany(
        "INSERT INTO payouts VALUES (?,?,?,?)",
        [(site, tournament_id, place, prize) for place, prize in enumerate(prizes, start=1)],
    )


def get_payouts(conn: PGConnection, site: str, tournament_id: str) -> list[float]:
    rows = conn.execute(
        "SELECT prize FROM payouts WHERE site=? AND tournament_id=? ORDER BY place",
        (site, tournament_id),
    ).fetchall()
    return [r[0] for r in rows]


def set_tournament_name(conn: PGConnection, site: str, tournament_id: str, name: str) -> None:
    """Só o nome — a hand history não trás isso (só o ID), então o
    vínculo nome<->ID é sempre manual (ex.: olhando a lista de torneios
    do site). Não usa `set_result` porque esse exige position/prize e
    sobrescreveria um resultado real já lançado."""
    conn.execute(
        """INSERT INTO tournaments (site, tournament_id, name)
           VALUES (?,?,?)
           ON CONFLICT(site, tournament_id) DO UPDATE SET name = excluded.name""",
        (site, tournament_id, name),
    )


def tournaments_with_payouts(conn: PGConnection) -> list[tuple]:
    return conn.execute(
        """SELECT DISTINCT t.site, t.tournament_id, t.name, t.buyin
           FROM tournaments t JOIN payouts p
             ON p.site = t.site AND p.tournament_id = t.tournament_id
           ORDER BY t.first_seen DESC"""
    ).fetchall()


# ---------------- Decision Analysis (Etapa 7 — Poker Decision Engine) ----------------
#
# Persistência opcional de uma análise já calculada (equity_engine +
# pot_odds + ev_engine + context, via replay_decision.py) — nunca
# recalcula nada aqui, só guarda o que já foi produzido. Sem `session_id`:
# não existe tabela de sessões no schema (sessões são calculadas
# dinamicamente por stats.py/bankroll.py) — inventar um id aqui seria
# persistir um dado que não existe de verdade. Tudo em BB (não em chips)
# pra ser comparável entre mãos com blind levels diferentes.

def save_decision_analysis(
    conn: PGConnection, *, site: str, hand_id: str, step_order: int,
    tournament_id: str | None, player: str, street: str, position: str | None,
    hero_cards: str | None, board: str | None,
    pot_before_action_bb: float | None, bet_faced_bb: float | None,
    call_cost_bb: float | None, effective_stack_bb: float | None,
    number_of_opponents: int | None, context_type: str, model_type: str,
    hero_equity: float | None, required_equity: float | None, pot_odds_ratio: str | None,
    ev_call_bb: float | None, ev_fold_bb: float | None, ev_push_bb: float | None,
    recommended_action: str | None, actual_action: str | None, actual_result_bb: float | None,
    assumptions: list[str],
) -> None:
    """Upsert de uma linha de decision_analysis (chave: site+hand_id+step_order
    — reanalisar o mesmo passo só atualiza a linha, não duplica)."""
    import datetime as _dt
    conn.execute(
        """INSERT INTO decision_analysis (
               site, hand_id, step_order, tournament_id, player, street, position,
               hero_cards, board, pot_before_action_bb, bet_faced_bb, call_cost_bb,
               effective_stack_bb, number_of_opponents, context_type, model_type,
               hero_equity, required_equity, pot_odds_ratio, ev_call_bb, ev_fold_bb,
               ev_push_bb, recommended_action, actual_action, actual_result_bb,
               assumptions, created_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT (site, hand_id, step_order) DO UPDATE SET
             tournament_id=excluded.tournament_id, player=excluded.player,
             street=excluded.street, position=excluded.position,
             hero_cards=excluded.hero_cards, board=excluded.board,
             pot_before_action_bb=excluded.pot_before_action_bb,
             bet_faced_bb=excluded.bet_faced_bb, call_cost_bb=excluded.call_cost_bb,
             effective_stack_bb=excluded.effective_stack_bb,
             number_of_opponents=excluded.number_of_opponents,
             context_type=excluded.context_type, model_type=excluded.model_type,
             hero_equity=excluded.hero_equity, required_equity=excluded.required_equity,
             pot_odds_ratio=excluded.pot_odds_ratio, ev_call_bb=excluded.ev_call_bb,
             ev_fold_bb=excluded.ev_fold_bb, ev_push_bb=excluded.ev_push_bb,
             recommended_action=excluded.recommended_action,
             actual_action=excluded.actual_action, actual_result_bb=excluded.actual_result_bb,
             assumptions=excluded.assumptions, created_at=excluded.created_at""",
        (site, hand_id, step_order, tournament_id, player, street, position,
         hero_cards, board, pot_before_action_bb, bet_faced_bb, call_cost_bb,
         effective_stack_bb, number_of_opponents, context_type, model_type,
         hero_equity, required_equity, pot_odds_ratio, ev_call_bb, ev_fold_bb,
         ev_push_bb, recommended_action, actual_action, actual_result_bb,
         json.dumps(assumptions),
         _dt.datetime.now().isoformat(timespec="seconds")),
    )
