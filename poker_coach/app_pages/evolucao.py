"""Evolução: o diferencial pedido — não é sintético. ROI por mês já
existia (stats.profit_by_period); acurácia Push/Fold por mês é NOVA
aqui, calculada retroativamente sobre suas mãos reais (não sobre quiz).
Push/Fold: sim. ICM: não (motor não existe, sem fingir número).

Também: comparador de 2 períodos (o "antes/depois de estudar" que você
pediu) — sem detecção automática de "quando comecei a estudar" (não
temos como saber isso sozinho), você escolhe as datas.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import stats  # noqa: E402
from poker_coach.ui import common  # noqa: E402

common.page_title("Evolução", "📅")

conn = common.require_conn()

st.subheader("Push/Fold: acurácia real por mês")
st.caption(
    "Calculado de novo sobre TODAS as suas mãos de abertura já importadas "
    "(não é do Modo Estudo) — mostra se você está realmente acertando mais "
    "push/fold com o tempo, não uma simulação."
)
if st.button("Calcular (roda o solver sobre todas as mãos)", type="primary"):
    from poker_coach.pushfold import analyze as pf
    prog = st.progress(0.0, text="Resolvendo...")

    def _progress(i, total):
        if total:
            prog.progress(min(i / total, 1.0), text=f"{i}/{total}")

    rows = pf.analyze_all(conn, progress=_progress)
    prog.empty()
    st.session_state["evo_rows"] = rows

rows = st.session_state.get("evo_rows")
if rows:
    from poker_coach.pushfold import analyze as pf
    monthly = pf.accuracy_by_period(rows, "month")
    if monthly:
        mdf = pd.DataFrame(monthly)
        st.dataframe(mdf.rename(columns={
            "period": "mês", "spots": "spots", "correct": "corretas",
            "accuracy_pct": "acurácia %", "ev_lost_bb": "EV perdido (BB)"
        }), width='stretch', hide_index=True)
        st.bar_chart(mdf.set_index("period")["accuracy_pct"])
        if len(monthly) >= 2:
            first, last = monthly[0], monthly[-1]
            delta = last["accuracy_pct"] - first["accuracy_pct"]
            if delta > 5:
                st.success(
                    f"📈 Sua acurácia Push/Fold foi de {first['accuracy_pct']}% "
                    f"em {first['period']} pra {last['accuracy_pct']}% em "
                    f"{last['period']} — melhora real de {delta:.1f} pontos."
                )
            elif delta < -5:
                st.warning(
                    f"📉 Sua acurácia caiu de {first['accuracy_pct']}% "
                    f"({first['period']}) pra {last['accuracy_pct']}% "
                    f"({last['period']})."
                )
    else:
        st.caption("Sem mãos com timestamp válido pra agrupar por mês.")
else:
    st.caption("Clique em Calcular pra ver a série real (pode levar alguns segundos).")

st.divider()
st.subheader("ROI por mês")
roi_rows = stats.profit_by_period(conn, "month")
if roi_rows:
    rdf = pd.DataFrame(roi_rows)
    st.dataframe(rdf, width='stretch', hide_index=True)
else:
    st.caption("Sem resultado de torneio registrado ainda.")

st.divider()
st.subheader("🎓 Acurácia no Modo Estudo, por mês")
qz = conn.execute(
    """SELECT substr(ts, 1, 7) AS mes, COUNT(*), SUM(correct)
       FROM quiz_log GROUP BY mes ORDER BY mes"""
).fetchall()
if qz:
    qdf = pd.DataFrame(
        [{"mês": m, "respondidas": n, "corretas": c, "acurácia %": round(c / n * 100, 1)}
         for m, n, c in qz])
    st.dataframe(qdf, width='stretch', hide_index=True)
    st.bar_chart(qdf.set_index("mês")["acurácia %"])
else:
    st.caption("Sem respostas no Modo Estudo ainda — vá em 🎓 Modo Estudo pra treinar.")

st.divider()
st.subheader("🀄 ICM")
st.caption("Motor de ICM ainda não implementado — sem esse dado aqui (página 🀄 ICM tem mais detalhe).")

st.divider()
st.subheader("Comparar dois períodos")
st.caption(
    "O \"antes de estudar / depois de 30 dias\" que você pediu — sem detecção "
    "automática de quando você começou a estudar (não temos como saber isso "
    "sozinho), então você escolhe as duas janelas de data."
)
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Período A**")
    a_from = st.date_input("De", key="cmp_a_from")
    a_to = st.date_input("Até", key="cmp_a_to")
with c2:
    st.markdown("**Período B**")
    b_from = st.date_input("De", key="cmp_b_from")
    b_to = st.date_input("Até", key="cmp_b_to")

if st.button("Comparar"):
    def _period_stats(d_from, d_to):
        row = conn.execute(
            """SELECT COUNT(*), SUM(buyin), SUM(COALESCE(prize,0))
               FROM tournaments
               WHERE finish_position IS NOT NULL AND DATE(first_seen) BETWEEN ? AND ?""",
            (str(d_from), str(d_to)),
        ).fetchone()
        n, invested, won = row
        roi = round((won - invested) / invested * 100, 1) if invested else None
        return {"torneios": n or 0, "ROI %": roi if roi is not None else "—"}

    a_stats = _period_stats(a_from, a_to)
    b_stats = _period_stats(b_from, b_to)
    cmp_df = pd.DataFrame([{"período": "A", **a_stats}, {"período": "B", **b_stats}])
    st.dataframe(cmp_df, width='stretch', hide_index=True)

conn.close()
