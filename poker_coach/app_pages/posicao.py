"""Dashboard por posição: VPIP/PFR/saldo em BB (disponível sempre) +
ROI/lucro em $ por posição quando houver resultados registrados.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import stats  # noqa: E402
from poker_coach.ui import common  # noqa: E402

common.page_title("Por Posição", "📍")

conn = common.require_conn()

rows = stats.position_stats(conn)
if not rows:
    st.info("Sem mãos com posição identificada ainda.")
    st.stop()

df = pd.DataFrame(rows).rename(columns={
    "position": "posição", "spots": "spots", "vpip_pct": "VPIP %",
    "pfr_pct": "PFR %", "net_bb": "saldo (BB)"})
st.dataframe(df, width='stretch', hide_index=True)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Saldo em BB por posição")
    st.bar_chart(df.set_index("posição")["saldo (BB)"])
with c2:
    st.subheader("VPIP / PFR por posição")
    st.bar_chart(df.set_index("posição")[["VPIP %", "PFR %"]])

worst = min(rows, key=lambda r: r["net_bb"])
best = max(rows, key=lambda r: r["net_bb"])
if worst["net_bb"] < 0:
    st.warning(
        f"⚠️ Sua pior posição é **{worst['position']}**: {worst['net_bb']:+.1f} BB "
        f"em {worst['spots']} mãos. Vale revisar as mãos jogadas nessa posição."
    )
if best["net_bb"] > 0:
    st.success(
        f"✅ Sua melhor posição é **{best['position']}**: {best['net_bb']:+.1f} BB "
        f"em {best['spots']} mãos."
    )

avg_vpip = sum(r["vpip_pct"] for r in rows) / len(rows)
outliers = [r for r in rows if abs(r["vpip_pct"] - avg_vpip) > 15 and r["spots"] >= 20]
for r in outliers:
    direction = "mais solto" if r["vpip_pct"] > avg_vpip else "mais fechado"
    st.caption(
        f"ℹ️ Você joga {direction} que sua média no **{r['position']}** "
        f"(VPIP {r['vpip_pct']}% vs média geral {avg_vpip:.1f}%)."
    )

conn.close()
