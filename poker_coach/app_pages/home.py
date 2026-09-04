"""Dashboard Geral — visão de conjunto (parte do grupo "Dashboard" na
barra lateral)."""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import stats  # noqa: E402
from poker_coach.ui import common  # noqa: E402

common.page_title("Dashboard Geral", "🏠")

conn = common.require_conn()

ov = stats.overview(conn)
r = stats.roi(conn)
hours = stats.hours_played(conn)

st.subheader("Visão geral")
row1 = st.columns(5)
row1[0].metric("Lucro total", f"{r['profit']:+.2f}" if r else "—")
row1[1].metric("ROI", f"{r['roi_pct']}%" if r else "—")
row1[2].metric("ITM", f"{r['itm_pct']}%" if r else "—")
row1[3].metric("ABI", f"{r['abi']:.2f}" if r else "—")
row1[4].metric("Torneios", ov["tournaments"])

by_period_day = stats.profit_by_period(conn, "day")
by_period_week = stats.profit_by_period(conn, "week")
by_period_month = stats.profit_by_period(conn, "month")
today = dt.date.today()
yesterday_key = (today - dt.timedelta(days=1)).strftime("%Y-%m-%d")
_iso = today.isocalendar()
week_key = f"{_iso.year}-W{_iso.week:02d}"  # combina com to_char(...,'IYYY-"W"IW') em stats.profit_by_period
month_key = today.strftime("%Y-%m")


def _lookup(rows, key):
    return next((x["profit"] for x in rows if x["period"] == key), None)


row2 = st.columns(5)
lm = _lookup(by_period_month, month_key)
lw = _lookup(by_period_week, week_key)
ly = _lookup(by_period_day, yesterday_key)
row2[0].metric("Lucro mês", f"{lm:+.2f}" if lm is not None else "—")
row2[1].metric("Lucro semana", f"{lw:+.2f}" if lw is not None else "—")
row2[2].metric("Lucro ontem", f"{ly:+.2f}" if ly is not None else "—")
row2[3].metric("Horas jogadas", f"{hours:.1f}h")
row2[4].metric("Mãos", f"{ov['hands']:,}")

row3 = st.columns(3)
row3[0].metric("BB ganhos (saldo em fichas)", f"{ov['net_bb']:+.1f} BB")
row3[1].metric("VPIP / PFR", f"{ov['vpip_pct']}% / {ov['pfr_pct']}%")
ct = stats.cash_vs_ticket_summary(conn)
row3[2].metric("🎟️ Tickets ganhos", f"{ct['ticket']['count']} (≈${ct['ticket']['total']:.2f})")

if r is None:
    st.info(
        "Lucro/ROI/ITM/ABI ainda não têm dado — registre o resultado dos seus "
        "torneios em **Configuração → Registrar resultado**. Enquanto isso, o "
        "saldo em BB abaixo já mostra sua evolução em fichas (derivado só da "
        "hand history)."
    )

st.divider()
st.subheader("Evolução")
tab1, tab2 = st.tabs(["Saldo em BB (sempre disponível)", "Lucro em $ (precisa de resultados)"])
with tab1:
    df = pd.read_sql_query(
        """SELECT ts, CAST(hero_net_chips AS REAL)/bb AS net_bb
           FROM hands WHERE bb > 0 AND ts IS NOT NULL ORDER BY ts""", conn.raw)
    if not df.empty:
        df["saldo_acumulado_bb"] = df["net_bb"].cumsum()
        st.line_chart(df.set_index(df.index)["saldo_acumulado_bb"])
    else:
        st.caption("Sem mãos com timestamp ainda.")
with tab2:
    if by_period_day:
        pdf = pd.DataFrame(by_period_day)
        pdf["lucro_acumulado"] = pdf["profit"].cumsum()
        st.line_chart(pdf.set_index("period")["lucro_acumulado"])
    else:
        st.caption("Sem resultados registrados ainda.")

st.divider()
st.subheader("Torneios")
tdf = pd.read_sql_query(
    """SELECT t.site AS sala, COALESCE(t.name, '') AS nome, t.tournament_id AS torneio,
              t.buyin AS buyin, COUNT(h.hand_id) AS maos,
              MIN(h.ts) AS inicio, MAX(h.ts) AS fim,
              CASE WHEN t.finish_position = 0 THEN NULL ELSE t.finish_position END AS posicao,
              t.prize AS premio, t.prize_type AS tipo
       FROM tournaments t
       LEFT JOIN hands h ON h.site = t.site AND h.tournament_id = t.tournament_id
       GROUP BY t.site, t.tournament_id ORDER BY inicio DESC""", conn.raw)
st.dataframe(tdf, width='stretch')
st.caption("Posição em branco = resultado conhecido mas posição exata não registrada "
           "(ex.: resultado lançado a partir do histórico do site, sem hand history).")

conn.close()
