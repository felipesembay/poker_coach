"""Fase 0 do plano de RL — auditoria do dataset ANTES de gerar o parquet
definitivo. Não grava nada, não assume número de linhas de antemão: só
percorre as mãos e conta o que existe de verdade.

Reaproveita `export.process_hand` (mesmo loop por mão que o export usa) —
a contagem reflete exatamente o que o dataset real vai conter, não uma
estimativa paralela."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import export as rl_export


@dataclass
class AuditReport:
    hands_total: int = 0
    hands_ok: int = 0
    hands_discarded_no_hero: int = 0
    hands_error: int = 0
    tournaments: int = 0

    decisions_total: int = 0
    decisions_by_street: Counter = field(default_factory=Counter)
    decisions_by_position: Counter = field(default_factory=Counter)
    decisions_by_action_class: Counter = field(default_factory=Counter)
    decisions_by_context_type: Counter = field(default_factory=Counter)
    decisions_reference_available: int = 0
    decisions_reference_unavailable: int = 0

    showdowns: int = 0
    errors: list[str] = field(default_factory=list)


def _tally(report: AuditReport, rows: list[dict]) -> None:
    if rows and rows[0]["showdown"]:
        report.showdowns += 1
    for row in rows:
        report.decisions_total += 1
        report.decisions_by_street[row["street"]] += 1
        report.decisions_by_position[row["position"]] += 1
        report.decisions_by_action_class[row["action_class"]] += 1
        report.decisions_by_context_type[row["context_type"]] += 1
        if row["reference_source"] == "unavailable":
            report.decisions_reference_unavailable += 1
        else:
            report.decisions_reference_available += 1


def run_audit(conn, *, site: str | None = None, progress=None) -> AuditReport:
    """Versão single-thread — usada nos testes (fixture pequeno). Pra
    volume real (milhares de mãos), use `run_audit_parallel`."""
    from .. import replay

    report = AuditReport()
    hands = replay.list_hands(conn, site=site)
    report.hands_total = len(hands)
    report.tournaments = len({h["tournament_id"] for h in hands})
    total = len(hands)

    for i, h in enumerate(hands):
        if progress:
            progress(i, total)
        rows, error = rl_export.process_hand(conn, h["site"], h["hand_id"])
        if error == "sem hero/cartas":
            report.hands_discarded_no_hero += 1
            continue
        if error is not None:
            report.hands_error += 1
            report.errors.append(f"{h['site']}/{h['hand_id']}: {error}")
            continue
        report.hands_ok += 1
        _tally(report, rows)

    return report


def run_audit_parallel(dsn: str, *, site: str | None = None,
                        workers: int | None = None, progress=None) -> AuditReport:
    """Mesmo resultado de `run_audit`, mas processa as mãos em paralelo
    (ver `export.export_dataset_parallel` — mesmo motivo/mesmo mecanismo:
    Monte Carlo do equity engine é CPU-bound e embaraçosamente paralelo
    por mão, sem GPU envolvida)."""
    import multiprocessing as mp
    import os

    from .. import db as dbm
    from .. import replay

    setup_conn = dbm.connect(dsn)
    hands = replay.list_hands(setup_conn, site=site)
    setup_conn.close()

    report = AuditReport()
    report.hands_total = len(hands)
    report.tournaments = len({h["tournament_id"] for h in hands})

    hand_refs = [(h["site"], h["hand_id"]) for h in hands]
    total = len(hand_refs)
    workers = workers or min(os.cpu_count() or 4, 16)

    with mp.Pool(processes=workers, initializer=rl_export._init_worker, initargs=(dsn,)) as pool:
        for i, (s, hid, rows, error) in enumerate(
            pool.imap_unordered(rl_export._process_hand_ref, hand_refs, chunksize=8)
        ):
            if progress:
                progress(i, total)
            if error == "sem hero/cartas":
                report.hands_discarded_no_hero += 1
                continue
            if error is not None:
                report.hands_error += 1
                report.errors.append(f"{s}/{hid}: {error}")
                continue
            report.hands_ok += 1
            _tally(report, rows)

    return report


def _fmt_counter(counter: Counter) -> str:
    lines = []
    for key, n in counter.most_common():
        lines.append(f"  {key!s:<24} {n:>7,}")
    return "\n".join(lines) if lines else "  (nenhum)"


def format_report(report: AuditReport) -> str:
    lines = [
        "=== Dataset Audit — RL Fase 0 ===",
        f"Hands total:              {report.hands_total:>7,}",
        f"Torneios:                 {report.tournaments:>7,}",
        f"Hands OK (usáveis):       {report.hands_ok:>7,}",
        f"Hands descartadas (sem hero/cartas): {report.hands_discarded_no_hero:>7,}",
        f"Hands com erro:           {report.hands_error:>7,}",
        f"Showdowns:                {report.showdowns:>7,}",
        "",
        f"Hero decision points:     {report.decisions_total:>7,}",
        "",
        "Distribuição por street:",
        _fmt_counter(report.decisions_by_street),
        "",
        "Distribuição por posição:",
        _fmt_counter(report.decisions_by_position),
        "",
        "Distribuição por action_class:",
        _fmt_counter(report.decisions_by_action_class),
        "",
        "Distribuição por context_type:",
        _fmt_counter(report.decisions_by_context_type),
        "",
        "Qualidade de referência (EV/Nash):",
        f"  com referência (nash/ev_engine):  {report.decisions_reference_available:>7,}",
        f"  sem referência (unavailable):     {report.decisions_reference_unavailable:>7,}",
    ]
    if report.errors:
        lines.append("")
        lines.append(f"Erros ({len(report.errors)}, mostrando até 20):")
        lines.extend(f"  {e}" for e in report.errors[:20])
    return "\n".join(lines)
