"""Motor de Push/Fold (Chip EV, Nash heads-up vs BB) — Fase 3 antecipada.

Uso rápido:
    from poker_coach.pushfold import analyze
    rows = analyze.analyze_all(conn)
    print(analyze.summarize(rows))

Ver docstrings de equity.py e nash.py pras limitações assumidas
(aproximação por combo representativo, vilão único = BB, chip EV sem ICM).
"""
from . import equity, nash, analyze  # noqa: F401
