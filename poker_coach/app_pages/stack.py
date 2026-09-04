"""Dashboard por faixa de stack: fold%/push%/call% preflop e saldo em BB
por bucket (0-5, 5-10, ..., 30-50 BB).
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import stats  # noqa: E402
from poker_coach.ui import common  # noqa: E402

common.page_title("Por Stack", "📊")

conn = common.require_conn()

rows = stats.stack_bucket_stats(conn)
df = pd.DataFrame(rows).rename(columns={
    "bucket": "faixa", "spots": "spots", "fold_pct": "fold %",
    "push_pct": "push %", "call_pct": "call %", "net_bb": "saldo (BB)"})
st.dataframe(df, width='stretch', hide_index=True)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Saldo em BB por faixa de stack")
    st.bar_chart(df.set_index("faixa")["saldo (BB)"])
with c2:
    st.subheader("Fold / Push / Call % por faixa")
    st.bar_chart(df.set_index("faixa")[["fold %", "push %", "call %"]])

valid = [r for r in rows if r["spots"] > 0]
if valid:
    worst = min(valid, key=lambda r: r["net_bb"])
    best = max(valid, key=lambda r: r["net_bb"])
    if worst["net_bb"] < 0:
        st.warning(
            f"⚠️ Faixa mais negativa: **{worst['bucket']}** "
            f"({worst['net_bb']:+.1f} BB em {worst['spots']} mãos). "
            f"Cruze com a página **🎯 Push/Fold** pra ver se é erro de decisão "
            f"(fold que devia empurrar, ou vice-versa) ou variância normal."
        )
    if best["net_bb"] > 0:
        st.success(f"✅ Faixa mais lucrativa: **{best['bucket']}** ({best['net_bb']:+.1f} BB).")

conn.close()
