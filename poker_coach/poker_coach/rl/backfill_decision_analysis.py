"""Fase 1B do plano de RL — popula `decision_analysis` pra todas as mãos já
importadas (hoje só tem 1 linha). Reaproveita o mesmo par
`analyze_hero_step`/`build_decision_analysis_record` que o export usa —
aqui só troca "acumular em DataFrame" por "gravar no banco via
`db.save_decision_analysis`" (upsert, então rodar de novo é seguro).

Continua mesmo se uma mão estiver malformada: conta e segue, nunca aborta
o batch inteiro por causa de uma mão só."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import export as rl_export
from .. import replay_decision


@dataclass
class BackfillStats:
    hands_seen: int = 0
    hands_ok: int = 0
    hands_discarded_no_hero: int = 0
    hands_error: int = 0
    decisions_saved: int = 0
    decisions_error: int = 0
    errors: list[str] = field(default_factory=list)


def backfill(conn, *, site: str | None = None, progress=None) -> BackfillStats:
    from .. import db as dbm
    from .. import replay

    stats = BackfillStats()
    hands = replay.list_hands(conn, site=site)
    total = len(hands)

    for i, h in enumerate(hands):
        stats.hands_seen += 1
        if progress:
            progress(i, total)
        try:
            rh = replay.load(conn, h["site"], h["hand_id"])
        except Exception as exc:  # noqa: BLE001
            stats.hands_error += 1
            stats.errors.append(f"{h['site']}/{h['hand_id']}: load falhou: {exc}")
            continue
        if rh is None or not rh.hero or not rh.hero_cards:
            stats.hands_discarded_no_hero += 1
            continue
        try:
            outcome = rl_export.compute_hand_outcome(conn, rh)
        except Exception as exc:  # noqa: BLE001
            stats.hands_error += 1
            stats.errors.append(f"{h['site']}/{h['hand_id']}: outcome falhou: {exc}")
            continue

        for step_index in rl_export.hero_decision_steps(rh):
            try:
                analysis = replay_decision.analyze_hero_step(rh, step_index)
                record = replay_decision.build_decision_analysis_record(
                    rh, step_index, analysis, actual_result_bb=outcome.actual_result_bb,
                )
                dbm.save_decision_analysis(conn, **record)
                stats.decisions_saved += 1
            except Exception as exc:  # noqa: BLE001
                stats.decisions_error += 1
                stats.errors.append(
                    f"{h['site']}/{h['hand_id']}#{step_index}: análise/gravação falhou: {exc}"
                )
        conn.commit()
        stats.hands_ok += 1

    return stats


def format_report(stats: BackfillStats) -> str:
    lines = [
        "=== Backfill decision_analysis ===",
        f"Hands processadas:        {stats.hands_seen:>7,}",
        f"Hands OK:                 {stats.hands_ok:>7,}",
        f"Hands descartadas (sem hero/cartas): {stats.hands_discarded_no_hero:>7,}",
        f"Hands com erro:           {stats.hands_error:>7,}",
        f"Decisões salvas:          {stats.decisions_saved:>7,}",
        f"Decisões com erro:        {stats.decisions_error:>7,}",
    ]
    if stats.errors:
        lines.append(f"Erros (mostrando até 20 de {len(stats.errors)}):")
        lines.extend(f"  {e}" for e in stats.errors[:20])
    return "\n".join(lines)
