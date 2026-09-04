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

CREATE INDEX IF NOT EXISTS idx_hands_trny ON hands(site, tournament_id);
CREATE INDEX IF NOT EXISTS idx_hands_stackbb ON hands(hero_stack_bb);
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


def set_result(conn, site: str, tournament_id: str, position: int, prize: float,
                prize_type: str = "cash", prize_note: str | None = None,
                name: str | None = None, buyin: float | None = None,
                currency: str | None = None, date_iso: str | None = None):
    """Registra o resultado de um torneio. prize_type: 'cash' ou 'ticket'
    (em satélites o prêmio costuma ser um bilhete — `prize` é o valor em
    $ real ou estimado, `prize_note` a descrição livre).

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


def tournaments_with_payouts(conn: PGConnection) -> list[tuple]:
    return conn.execute(
        """SELECT DISTINCT t.site, t.tournament_id, t.name, t.buyin
           FROM tournaments t JOIN payouts p
             ON p.site = t.site AND p.tournament_id = t.tournament_id
           ORDER BY t.first_seen DESC"""
    ).fetchall()
