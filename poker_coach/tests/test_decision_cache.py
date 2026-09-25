"""Testes do cache de Decision Analysis (Replayer) — db.get_cached_decision/
save_cached_decision e o comportamento de cache no endpoint
GET /api/replayer/{site}/{hand_id}/decision/{step}.

Não usa uma mão real (o cálculo ao vivo leva 10-16s, medido nesta sessão)
— monkeypatch em `analyze_hero_step` pra contar chamadas e confirmar que
o 2º request pra MESMA mão/step não recomputa, sem pagar o custo real."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm
from poker_coach.parsers import partypoker

TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"
ROOT = pathlib.Path(__file__).resolve().parents[1]


def _reset(conn):
    for t in ["actions", "seats", "showdowns", "results", "hands", "tournaments", "decision_cache"]:
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


def test_get_and_save_cached_decision_roundtrip():
    conn = dbm.connect(TEST_DSN)
    _reset(conn)

    assert dbm.get_cached_decision(conn, "s", "h1", 3) is None

    dbm.save_cached_decision(conn, "s", "h1", 3, '{"a": 1}')
    conn.commit()
    assert dbm.get_cached_decision(conn, "s", "h1", 3) == '{"a": 1}'

    # upsert: mesma chave, conteudo novo substitui, nao duplica.
    dbm.save_cached_decision(conn, "s", "h1", 3, '{"a": 2}')
    conn.commit()
    assert dbm.get_cached_decision(conn, "s", "h1", 3) == '{"a": 2}'
    n = conn.execute(
        "SELECT COUNT(*) FROM decision_cache WHERE site='s' AND hand_id='h1' AND step_order=3"
    ).fetchone()[0]
    assert n == 1


def test_get_decision_endpoint_caches_after_first_call(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app
    from api.routers import replayer as replayer_router

    # replayer.py::_conn() usa o DSN de produção HARDCODED (não é
    # Depends() injetável) — sem isso, o TestClient bateria no Postgres
    # de produção mesmo com os dados de teste inseridos aqui no TEST_DSN,
    # deixando o teste dependente de estado alheio (achado real: rodou
    # contra prod na primeira tentativa e deu cache HIT falso-positivo,
    # de uma chamada manual anterior desta sessão que tinha esquentado o
    # cache de produção pra essa mesma mão).
    monkeypatch.setattr(replayer_router, "_conn", lambda: dbm.connect(TEST_DSN))

    conn = dbm.connect(TEST_DSN)
    _reset(conn)
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())
    for h in hands:
        dbm.insert_hand(conn, h)
    conn.commit()
    h0 = hands[0]

    # acha um passo real de decisao do hero pra essa mao (sem rodar o
    # motor de EV/Nash de verdade — so precisamos de um site/hand_id/step
    # validos pra bater na rota; a resposta em si vem do fake abaixo).
    from poker_coach import replay, replay_decision
    rh = replay.load(conn, h0.site, h0.hand_id)
    step_index = next(
        i for i, s in enumerate(rh.steps)
        if s.player == rh.hero and s.action not in replay_decision.NON_DECISION_ACTIONS
    )

    call_count = {"n": 0}
    real_analyze = replayer_router.replay_decision.analyze_hero_step

    def _counting_analyze(*args, **kwargs):
        call_count["n"] += 1
        return real_analyze(*args, **kwargs)

    monkeypatch.setattr(replayer_router.replay_decision, "analyze_hero_step", _counting_analyze)

    client = TestClient(app)
    url = f"/api/replayer/{h0.site}/{h0.hand_id}/decision/{step_index}"

    r1 = client.get(url)
    assert r1.status_code == 200
    assert call_count["n"] == 1

    r2 = client.get(url)
    assert r2.status_code == 200
    assert call_count["n"] == 1  # NAO recomputou — serviu do cache
    assert r1.json() == r2.json()

    r3 = client.get(url, params={"force_recompute": True})
    assert r3.status_code == 200
    assert call_count["n"] == 2  # force_recompute ignora o cache
