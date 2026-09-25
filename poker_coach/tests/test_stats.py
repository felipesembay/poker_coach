"""Testes de poker_coach/stats.py::stack_bucket_stats contra o Postgres
de teste — mesmo padrão de test_bankroll.py (dados sintéticos inseridos
direto nas tabelas).

Regressão específica: a reescrita pra uma query só (LEFT JOIN LATERAL,
tirando o N+1 de "1 query por mão num loop Python") tem que preservar a
semântica exata do código original pra mãos SEM nenhuma ação preflop
voluntária do hero (ex.: hero só postou blind, todo mundo foldou antes
dele agir) — essas mãos ainda contam em `spots`, só não entram no
denominador de fold/push/call %. Um INNER JOIN LATERAL (em vez de LEFT)
faria essas mãos desaparecerem de `spots` também — é exatamente esse bug
que este teste trava."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm
from poker_coach import stats

TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"
SITE = "testsite"


def _reset(conn):
    for t in ["actions", "seats", "showdowns", "results", "hands", "tournaments"]:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


def _insert_hand(conn, hand_id, hero_stack_bb, hero_net_chips, bb=100):
    conn.execute(
        """INSERT INTO hands (site, hand_id, tournament_id, hero, hero_stack_bb,
                               hero_net_chips, bb, favorite)
           VALUES (?,?,?,?,?,?,?,0)""",
        (SITE, hand_id, "T1", "Hero", hero_stack_bb, hero_net_chips, bb),
    )


def _insert_action(conn, hand_id, ord_, street, player, action, amount=0, all_in=False):
    conn.execute(
        "INSERT INTO actions (site, hand_id, ord, street, player, action, amount, all_in) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (SITE, hand_id, ord_, street, player, action, amount, int(all_in)),
    )


def test_stack_bucket_stats_counts_folds_pushes_and_calls():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)

    # 3 maos na faixa 10-15 BB: 1 fold, 1 push (raise all-in), 1 call.
    _insert_hand(conn, "h1", 12.0, -100)
    _insert_action(conn, "h1", 1, "preflop", "Hero", "fold")

    _insert_hand(conn, "h2", 13.0, 1200)
    _insert_action(conn, "h2", 1, "preflop", "Hero", "raise", 1300, all_in=True)

    _insert_hand(conn, "h3", 14.0, -50)
    _insert_action(conn, "h3", 1, "preflop", "Hero", "call", 100)

    conn.commit()

    out = {row["bucket"]: row for row in stats.stack_bucket_stats(conn)}
    bucket = out["10-15BB"]
    assert bucket["spots"] == 3
    assert bucket["fold_pct"] == 33.3
    assert bucket["push_pct"] == 33.3
    assert bucket["call_pct"] == 33.3
    assert bucket["net_bb"] == round((-100 - 50 + 1200) / 100, 1)


def test_stack_bucket_stats_hand_without_voluntary_preflop_action_still_counts_as_spot():
    """Mão onde o hero só postou blind e todo mundo foldou antes dele agir
    de novo (sem nenhuma linha em `actions` fora post_sb/post_bb/post_ante
    pro hero) — regressão do LEFT JOIN LATERAL."""
    conn = dbm.connect(TEST_DSN)
    _reset(conn)

    _insert_hand(conn, "h1", 11.0, 10)
    _insert_action(conn, "h1", 1, "preflop", "Hero", "post_bb", 10)
    _insert_action(conn, "h1", 2, "preflop", "Villain", "fold")
    # hero nunca age de novo (mão resolvida sem ele voltar a decidir)
    conn.commit()

    out = {row["bucket"]: row for row in stats.stack_bucket_stats(conn)}
    bucket = out["10-15BB"]
    assert bucket["spots"] == 1  # a mao AINDA conta como spot na faixa
    assert bucket["fold_pct"] is None  # mas nao entra no denominador de %
    assert bucket["push_pct"] is None
    assert bucket["call_pct"] is None


def test_stack_bucket_stats_empty_bucket_returns_zero_not_none_spots():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    out = {row["bucket"]: row for row in stats.stack_bucket_stats(conn)}
    for row in out.values():
        assert row["spots"] == 0
        assert row["fold_pct"] is None
        assert row["net_bb"] == 0.0
