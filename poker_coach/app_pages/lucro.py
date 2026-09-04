"""Dashboard de Lucro: diário/semanal/mensal e por buy-in (precisa de
resultados registrados) + saldo em BB por horário/dia da semana (não
precisa) + resumo dinheiro vs ticket."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import stats  # noqa: E402
from poker_coach.ui import common  # noqa: E402

common.page_title("Lucro", "💰")

conn = common.require_conn()

st.subheader("Saldo em BB por horário do dia")
st.caption("Não depende de resultado registrado — só da hand history. "
           "É aqui que aparece se você joga muito melhor às 19h do que à meia-noite.")
hour_rows = stats.net_bb_by_hour(conn)
if hour_rows:
    hdf = pd.DataFrame(hour_rows)
    st.bar_chart(hdf.set_index("hour")["net_bb"])
    best_h = max(hour_rows, key=lambda r: r["net_bb"])
    worst_h = min(hour_rows, key=lambda r: r["net_bb"])
    if best_h["hands"] >= 20 and worst_h["hands"] >= 20 and best_h["net_bb"] > worst_h["net_bb"]:
        st.info(
            f"💡 Você ganha mais jogando às **{best_h['hour']}h** "
            f"({best_h['net_bb']:+.1f} BB) do que às **{worst_h['hour']}h** "
            f"({worst_h['net_bb']:+.1f} BB)."
        )
else:
    st.caption("Sem mãos com horário ainda.")

st.subheader("Saldo em BB por dia da semana")
wd_rows = stats.net_bb_by_weekday(conn)
if wd_rows:
    wdf = pd.DataFrame(wd_rows)
    st.bar_chart(wdf.set_index("weekday")["net_bb"])

st.divider()
st.subheader("💵 Dinheiro vs 🎟️ Ticket")
ct = stats.cash_vs_ticket_summary(conn)
conv = stats.satellite_conversion_rate(conn)
c1, c2, c3 = st.columns(3)
c1.metric("Ganho em dinheiro", f"${ct['cash']['total']:.2f}", f"{ct['cash']['count']} torneios")
c2.metric("Ganho em tickets (valor estimado)", f"${ct['ticket']['total']:.2f}",
          f"{ct['ticket']['count']} conversões")
c3.metric("Conversão em satélites", f"{conv['pct']}%" if conv["pct"] is not None else "—",
          f"{conv['converted']}/{conv['attempts']} tentativas")
sat = stats.satellite_history(conn)
if sat:
    st.dataframe(pd.DataFrame(sat), width='stretch', hide_index=True)
    st.caption(
        "Tickets entram no lucro/ROI pelo valor estimado que você informou ao "
        "registrar o resultado — ajuste na página de Configuração se o valor "
        "real do bilhete for diferente."
    )

st.divider()
r = stats.roi(conn)
if r is None:
    st.info(
        "Lucro em $ precisa de resultado registrado por torneio "
        "(posição final + prêmio) — vá em **⚙️ Configuração**."
    )
else:
    st.subheader("Lucro por período ($)")
    period = st.radio("Agrupar por", ["day", "week", "month"], horizontal=True,
                       format_func=lambda p: {"day": "Dia", "week": "Semana", "month": "Mês"}[p])
    rows = stats.profit_by_period(conn, period)
    if rows:
        pdf = pd.DataFrame(rows)
        st.bar_chart(pdf.set_index("period")["profit"])
        st.dataframe(pdf, width='stretch', hide_index=True)

    st.subheader("Lucro por buy-in ($)")
    brows = stats.profit_by_buyin(conn)
    if brows:
        bdf = pd.DataFrame(brows)
        st.bar_chart(bdf.set_index("buyin")["profit"])
        st.dataframe(bdf, width='stretch', hide_index=True)
        best_b = max(brows, key=lambda x: x["profit"])
        worst_b = min(brows, key=lambda x: x["profit"])
        if worst_b["profit"] < 0 and worst_b != best_b:
            st.warning(
                f"⚠️ Você perde dinheiro no buy-in **{worst_b['buyin']}** "
                f"({worst_b['profit']:+.2f}, ROI {worst_b['roi_pct']}%)."
            )

conn.close()
