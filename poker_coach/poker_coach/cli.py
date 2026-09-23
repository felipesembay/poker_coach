"""CLI do Poker Coach.

Uso:
  python -m poker_coach.cli import <arquivo.txt> [--db <dsn>]
  python -m poker_coach.cli report [--db <dsn>]
  python -m poker_coach.cli result <site> <tournament_id> <posicao> <premio> [--db <dsn>]

`--db` é uma connection string do Postgres, ex.:
  postgresql://postgres:airflow@172.17.0.3:5432/poker_coach

O importador detecta a sala automaticamente e é incremental:
mãos já importadas são ignoradas.
"""
import argparse
import sys
from pathlib import Path

from . import db as dbm
from . import stats
from .parsers import partypoker, pokerstars


def detect_site(text: str) -> str | None:
    if "PokerStars" in text[:2000]:
        return "pokerstars"
    if "Hand History For Game" in text[:2000] or "Hand History for Game" in text[:2000]:
        return "partypoker"
    return None


def cmd_import(args):
    text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    site = detect_site(text)
    if site is None:
        print("Não reconheci o formato do arquivo. Envie um exemplo para calibrar o parser.")
        sys.exit(1)
    parser = pokerstars if site == "pokerstars" else partypoker
    hands = parser.parse_file(text)
    conn = dbm.connect(args.db)
    new = sum(dbm.insert_hand(conn, h) for h in hands)
    conn.commit()
    print(f"Sala: {site} | mãos no arquivo: {len(hands)} | novas importadas: {new}")


def cmd_pushfold(args):
    from .pushfold import analyze as pf

    conn = dbm.connect(args.db)

    def progress(i, total):
        if total and i % 50 == 0:
            print(f"  ...{i}/{total}", file=sys.stderr)

    print("Resolvendo Nash push/fold sobre as mãos de abertura importadas "
          f"(stack efetivo {args.bb_min}-{args.bb_max} BB, vilão = BB)...")
    rows = pf.analyze_all(conn, bb_min=args.bb_min, bb_max=args.bb_max, progress=progress)
    s = pf.summarize(rows)
    print(f"\n=== Push/Fold — {s['spots']} spots analisados ===")
    print(f"EV perdido total: {s['total_ev_lost_bb']} BB em {s['leak_spots']} spots com decisão errada")
    print("\nPor posição:")
    for pos, d in sorted(s["by_position"].items(), key=lambda kv: -kv[1]["ev_lost_bb"]):
        print(f"  {pos:<5} spots: {d['spots']:>4} | leaks: {d['leaks']:>3} | EV perdido: {d['ev_lost_bb']:+.1f} BB")
    print("\nPiores mãos (mais EV perdido):")
    for r in s["worst"]:
        print(f"  [{r.site}] {r.hand_id} | {r.position:<4} {r.hero_cards:<6} "
              f"| stack ef.: {r.effective_bb}BB | você: {r.hero_decision} | Nash: {r.nash_decision} "
              f"| EV do push: {r.ev_push_bb:+.2f} BB | perdeu {r.ev_lost_bb:.2f} BB")


def cmd_audit_rl(args):
    from .rl import audit as rl_audit

    def progress(i, total):
        if total and i % 200 == 0:
            print(f"  ...{i}/{total}", file=sys.stderr, flush=True)

    print(f"Auditando dataset de decisão do hero (Fase 0 do plano de RL, {args.workers} workers)...")
    report = rl_audit.run_audit_parallel(args.db, site=args.site, workers=args.workers, progress=progress)
    print()
    print(rl_audit.format_report(report))


def cmd_export_rl(args):
    from .rl import export as rl_export

    def progress(i, total):
        if total and i % 200 == 0:
            print(f"  ...{i}/{total}", file=sys.stderr, flush=True)

    print(f"Exportando dataset de decisão do hero para {args.out} "
          f"({args.format}, {args.workers} workers, "
          f"{args.equity_iterations or 'default'} iterações de equity"
          f"{', retomando checkpoint existente' if args.resume else ''})...")
    stats = rl_export.export_dataset_parallel(
        args.db, args.out, site=args.site, format=args.format,
        workers=args.workers, equity_iterations=args.equity_iterations,
        resume=args.resume, progress=progress,
    )
    print(f"Mãos: {stats.hands_ok} OK, {stats.hands_discarded_no_hero} descartadas "
          f"(sem hero/cartas), {stats.hands_error} com erro")
    print(f"Decisões exportadas: {stats.decisions}")
    if stats.errors:
        print(f"Erros (mostrando até 20 de {len(stats.errors)}):")
        for e in stats.errors[:20]:
            print(f"  {e}")


def cmd_backfill_decision_analysis(args):
    from .rl import backfill_decision_analysis as rl_backfill

    conn = dbm.connect(args.db)

    def progress(i, total):
        if total and i % 500 == 0:
            print(f"  ...{i}/{total}", file=sys.stderr)

    print("Populando decision_analysis a partir de todas as mãos importadas...")
    stats = rl_backfill.backfill(conn, site=args.site, progress=progress)
    print()
    print(rl_backfill.format_report(stats))


def cmd_leak_report(args):
    import pandas as pd

    from .rl import leak_detector as ld

    df = pd.read_parquet(args.dataset)
    report = ld.build_leak_report(df)
    print(ld.format_leak_report(report, min_confidence=args.min_confidence))


def cmd_train_bc(args):
    import pandas as pd

    from .rl import personal_policy as pp

    print(f"Carregando dataset de {args.dataset}...")
    df = pd.read_parquet(args.dataset)
    report, pipeline = pp.train_and_evaluate(df)
    print()
    print(pp.format_report(report))
    if args.out:
        pp.save_policy(pipeline, args.out)
        print(f"\nPersonal Policy salva em {args.out}")


def cmd_result(args):
    conn = dbm.connect(args.db)
    dbm.set_result(conn, args.site, args.tournament_id, args.position, args.prize)
    conn.commit()
    print("Resultado registrado.")


def cmd_report(args):
    conn = dbm.connect(args.db)
    ov = stats.overview(conn)
    print("=== Visão geral ===")
    print(f"Mãos: {ov['hands']} | Torneios: {ov['tournaments']}")
    print(f"VPIP: {ov['vpip_pct']}% | PFR: {ov['pfr_pct']}% | Saldo: {ov['net_bb']} BB")

    r = stats.roi(conn)
    print("\n=== ROI ===")
    if r:
        print(f"Torneios com resultado: {r['tournaments']} | ABI: {r['abi']}")
        print(f"Investido: {r['invested']} | Ganho: {r['won']} | Lucro: {r['profit']}")
        print(f"ROI: {r['roi_pct']}% | ITM: {r['itm_pct']}%")
    else:
        print("Sem resultados registrados ainda. Use o comando 'result'.")

    print("\n=== Torneios ===")
    for site, tid, buyin, hands, first, last, pos, prize in stats.per_tournament(conn):
        res = f"{pos}º, prêmio {prize}" if pos else "sem resultado"
        print(f"[{site}] {tid} | buy-in {buyin} | {hands} mãos | {first} → {last} | {res}")

    print("\n=== Comportamento short stack (8–20 BB) preflop ===")
    rep = stats.shortstack_fold_report(conn)
    if not rep:
        print("Sem mãos nessa faixa de stack ainda.")
    for row in rep:
        uf = row["unopened_fold_pct"]
        uf_s = f" | fold em pote aberto: {uf}%" if uf is not None else ""
        print(f"{row['position']:<5} spots: {row['spots']:>4} | fold: {row['fold_pct']}% "
              f"| shove: {row['shove_pct']}% | raise: {row['raise_pct']}%{uf_s}")


def main():
    p = argparse.ArgumentParser(prog="poker_coach")
    p.add_argument("--db", default="postgresql://postgres:airflow@172.17.0.3:5432/poker_coach")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("import")
    pi.add_argument("file")
    pi.set_defaults(func=cmd_import)

    pr = sub.add_parser("report")
    pr.set_defaults(func=cmd_report)

    ps = sub.add_parser("result")
    ps.add_argument("site")
    ps.add_argument("tournament_id")
    ps.add_argument("position", type=int)
    ps.add_argument("prize", type=float)
    ps.set_defaults(func=cmd_result)

    pf = sub.add_parser("pushfold", help="Nash push/fold sobre spots de abertura já importados")
    pf.add_argument("--bb-min", type=float, default=5.0, dest="bb_min")
    pf.add_argument("--bb-max", type=float, default=25.0, dest="bb_max")
    pf.set_defaults(func=cmd_pushfold)

    pa = sub.add_parser("audit-rl", help="Fase 0 do plano de RL: audita o dataset de decisão do hero")
    pa.add_argument("--site", default=None)
    pa.add_argument("--workers", type=int, default=None, help="padrão: min(cpus, 16)")
    pa.set_defaults(func=cmd_audit_rl)

    pe = sub.add_parser("export-rl", help="Fase 1 do plano de RL: exporta o dataset de decisão do hero")
    pe.add_argument("--out", required=True)
    pe.add_argument("--site", default=None)
    pe.add_argument("--format", choices=["parquet", "csv"], default="parquet")
    pe.add_argument("--workers", type=int, default=None, help="padrão: min(cpus, 16)")
    pe.add_argument("--equity-iterations", type=int, default=None, dest="equity_iterations",
                     help="padrão: DEFAULT_MC_ITERATIONS do equity engine (20000). "
                          "Reduzir troca precisão de hero_equity/ev_gap por velocidade "
                          "(ex.: 2000) — ação/behavior do dataset não é afetada.")
    pe.add_argument("--resume", action="store_true",
                     help="se --out já existe, pula as mãos já presentes nele e só "
                          "processa o resto (não reprocessa do zero um export interrompido)")
    pe.set_defaults(func=cmd_export_rl)

    pb = sub.add_parser("backfill-decision-analysis",
                         help="Fase 1B do plano de RL: popula decision_analysis pra todas as mãos")
    pb.add_argument("--site", default=None)
    pb.set_defaults(func=cmd_backfill_decision_analysis)

    pt = sub.add_parser("train-bc", help="Fase 2 do plano de RL: treina a Personal Policy (Behavioral Cloning)")
    pt.add_argument("--dataset", required=True, help="parquet gerado por export-rl")
    pt.add_argument("--out", default=None, help="onde salvar o modelo treinado (joblib .pkl)")
    pt.set_defaults(func=cmd_train_bc)

    pl = sub.add_parser("leak-report", help="Fase 3 do plano de RL: relatório do Leak Detector")
    pl.add_argument("--dataset", required=True, help="parquet gerado por export-rl")
    pl.add_argument("--min-confidence", choices=["baixa", "média", "alta"], default="média",
                     dest="min_confidence")
    pl.set_defaults(func=cmd_leak_report)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
