"""Testes de export_dataset_parallel/resume contra o Postgres de teste
(mesmo fixture real do PartyPoker usado em test_rl_audit.py).

Cobre o que a versão paralela adiciona sobre `export_dataset` (já testado
em test_rl_export.py): checkpoint incremental atômico e retomada
(`resume=True`) sem reprocessar mãos já presentes no arquivo — motivado
por um export real de produção ter sido interrompido por um reboot de
máquina no meio da execução."""
import pathlib
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm
from poker_coach.parsers import partypoker
from poker_coach.rl import export as rl_export

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"


def _load_fixture(conn):
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())
    for t in ["actions", "seats", "showdowns", "results", "hands", "tournaments"]:
        conn.execute(f"DELETE FROM {t}")
    for h in hands:
        dbm.insert_hand(conn, h)
    conn.commit()
    return hands


def test_export_dataset_parallel_matches_serial(tmp_path):
    conn = dbm.connect(TEST_DSN)
    hands = _load_fixture(conn)

    out = tmp_path / "parallel.parquet"
    stats = rl_export.export_dataset_parallel(
        TEST_DSN, str(out), site="partypoker", workers=2, equity_iterations=300,
    )
    assert stats.hands_ok == len(hands)
    assert stats.errors == []

    df = pd.read_parquet(out)
    assert len(df) == stats.decisions
    assert set(df["hand_id"]) == {h.hand_id for h in hands}


def test_export_dataset_parallel_resume_skips_already_done_hands(tmp_path):
    conn = dbm.connect(TEST_DSN)
    hands = _load_fixture(conn)
    out = tmp_path / "resume.parquet"

    # simula um checkpoint parcial de um export interrompido: só a
    # primeira mão, com uma coluna sentinela pra provar que essa linha
    # foi PRESERVADA (não reprocessada) pelo resume.
    partial = pd.DataFrame([{
        "site": hands[0].site, "hand_id": hands[0].hand_id, "step_order": 999,
        "sentinel": "veio-do-checkpoint-antigo",
    }])
    partial.to_parquet(out, index=False)

    stats = rl_export.export_dataset_parallel(
        TEST_DSN, str(out), site="partypoker", workers=2,
        equity_iterations=300, resume=True,
    )

    # só a mão QUE FALTAVA foi processada nesta chamada.
    assert stats.hands_seen == len(hands) - 1

    df = pd.read_parquet(out)
    assert set(df["hand_id"]) == {h.hand_id for h in hands}
    sentinel_rows = df[df["hand_id"] == hands[0].hand_id]
    assert (sentinel_rows["sentinel"] == "veio-do-checkpoint-antigo").any()


def test_export_dataset_parallel_checkpoints_mid_run(tmp_path):
    """checkpoint_every=1 força um checkpoint a cada mão — se o processo
    fosse morto no meio (como aconteceu de verdade em produção), o
    arquivo em disco já teria as mãos processadas até ali, não vazio."""
    conn = dbm.connect(TEST_DSN)
    hands = _load_fixture(conn)
    out = tmp_path / "checkpointed.parquet"

    rl_export.export_dataset_parallel(
        TEST_DSN, str(out), site="partypoker", workers=2,
        equity_iterations=300, checkpoint_every=1,
    )
    assert out.exists()
    df = pd.read_parquet(out)
    assert set(df["hand_id"]) == {h.hand_id for h in hands}
