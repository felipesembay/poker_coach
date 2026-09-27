"""Testes de api/routers/play_style.py — sem banco: `_features` é trocado por
um DataFrame sintético, então o teste cobre só a camada HTTP (validação de
parâmetros, filtros combinados, serialização com n/opps e NaN -> null)."""
import pathlib
import sys

import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from api.main import app  # noqa: E402
from api.routers import play_style  # noqa: E402
from poker_coach import player_stats as ps  # noqa: E402


def _df():
    base = dict.fromkeys(ps.FLAG_COLUMNS, 0)
    rows = [
        # T1 ($5.50): CO 8–12 BB, abre (ATS) e dá c-bet
        {"hand_id": "h1", "tournament_id": "T1", "buyin": 5.5, "ts": "2026-09-01T10:00:00",
         "stack_range": "8–12 BB", "position": "CO",
         "vpip_opp": 1, "vpip": 1, "pfr": 1, "ats_opp": 1, "ats": 1, "cbet_opp": 1, "cbet": 1},
        # T1: CO 8–12 BB, fold
        {"hand_id": "h2", "tournament_id": "T1", "buyin": 5.5, "ts": "2026-09-01T10:05:00",
         "stack_range": "8–12 BB", "position": "CO", "vpip_opp": 1, "ats_opp": 1},
        # T2 ($1.10): BB 30+ BB, walk
        {"hand_id": "h3", "tournament_id": "T2", "buyin": 1.1, "ts": "2026-09-10T20:00:00",
         "stack_range": "30+ BB", "position": "BB"},
    ]
    df = pd.DataFrame([{**base, "site": "s", "tournament_name": None, "n_players": 6,
                        "stack_bb": 10.0, **r} for r in rows])
    df["ts"] = pd.to_datetime(df["ts"])
    return df


@pytest.fixture
def client(monkeypatch):
    df = _df()
    monkeypatch.setattr(play_style, "_features", lambda: df)
    return TestClient(app)


def test_options(client):
    o = client.get("/api/play-style/options").json()
    assert o["buyins"] == [1.1, 5.5]
    assert o["positions"] == ["CO", "BB"]
    assert o["stack_ranges"] == ps.STACK_LABELS
    assert {t["tournament_id"] for t in o["tournaments"]} == {"T1", "T2"}
    assert [m["key"] for m in o["metrics"]] == list(ps.METRICS)


def test_report_all_has_samples_and_nulls(client):
    j = client.get("/api/play-style/report").json()
    s = j["summary"]
    assert s["hands"] == 3 and s["tournaments"] == 2
    assert s["vpip"] == {"pct": 50.0, "made": 1, "opps": 2}
    assert s["gap"] == 0.0
    assert s["f3b"] == {"pct": None, "made": 0, "opps": 0}
    assert [r["position"] for r in j["by_position"]] == ["CO", "BB"]
    bb = j["by_position"][1]
    assert bb["vpip"] is None and bb["vpip_n"] == 0 and bb["hands"] == 1


def test_report_filters_combine(client):
    j = client.get("/api/play-style/report",
                   params={"buyin": 5.5, "stack": "8–12 BB", "position": "CO"}).json()
    assert j["summary"]["hands"] == 2
    assert j["summary"]["ats"] == {"pct": 50.0, "made": 1, "opps": 2}
    assert len(j["table"]) == 1
    j = client.get("/api/play-style/report", params={"buyin": 5.5, "position": "BB"}).json()
    assert j["summary"]["hands"] == 0 and j["table"] == []
    j = client.get("/api/play-style/report", params={"site": "s", "tournament_id": "T2"}).json()
    assert j["summary"]["hands"] == 1


def test_report_custom_period_and_evolution(client):
    j = client.get("/api/play-style/report", params={
        "period": "custom", "date_from": "2026-09-01", "date_to": "2026-09-01", "freq": "D"}).json()
    assert j["summary"]["hands"] == 2
    assert [e["period"] for e in j["evolution"]] == ["2026-09-01"]


def test_report_validation(client):
    assert client.get("/api/play-style/report", params={"stack": "9 BB"}).status_code == 400
    assert client.get("/api/play-style/report", params={"period": "custom"}).status_code == 400
    assert client.get("/api/play-style/report", params={"tournament_id": "T1"}).status_code == 400
