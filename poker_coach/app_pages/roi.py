"""Dashboard de ROI: por buy-in, com o texto de insight pedido
("seu limite ideal atualmente é US$X") em vez de só números soltos.
Precisa de resultados registrados (posição final + prêmio por torneio).
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import stats  # noqa: E402
from poker_coach.ui import common  # noqa: E402

common.page_title("ROI", "📈")

conn = common.require_conn()

r = stats.roi(conn)
if r is None:
    st.info(
        "Sem resultado registrado ainda. Vá em **⚙️ Configuração** "
        "e registre posição final + prêmio dos torneios já importados."
    )
    conn.close()
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("ROI geral", f"{r['roi_pct']}%")
c2.metric("ITM", f"{r['itm_pct']}%")
c3.metric("ABI", f"{r['abi']:.2f}")
c4.metric("Torneios com resultado", r["tournaments"])

st.divider()
st.subheader("ROI por buy-in")
brows = stats.profit_by_buyin(conn)
MIN_SAMPLE = 5  # abaixo disso o ROI é ruído, não dá pra confiar
if not brows:
    st.caption("Sem dados.")
else:
    bdf = pd.DataFrame(brows)
    st.dataframe(bdf.rename(columns={
        "buyin": "buy-in", "tournaments": "torneios", "profit": "lucro",
        "roi_pct": "ROI %", "itm_pct": "ITM %"}), width='stretch', hide_index=True)
    reliable = [b for b in brows if b["tournaments"] >= MIN_SAMPLE and b["roi_pct"] is not None]
    st.bar_chart(bdf.set_index("buyin")["roi_pct"])

    if len(reliable) >= 2:
        best = max(reliable, key=lambda b: b["roi_pct"])
        worst = min(reliable, key=lambda b: b["roi_pct"])
        st.markdown("### 💡 Insight")
        if worst["roi_pct"] < 0 <= best["roi_pct"]:
            st.warning(
                f"Seu ROI vira negativo acima de **{worst['buyin']}** "
                f"({worst['roi_pct']}%, {worst['tournaments']} torneios). "
                f"Seu limite ideal hoje parece ser em torno de **{best['buyin']}** "
                f"(ROI {best['roi_pct']}%)."
            )
        elif best["roi_pct"] - worst["roi_pct"] > 20:
            st.info(
                f"Seu ROI cai de **{best['roi_pct']}%** no buy-in {best['buyin']} "
                f"pra **{worst['roi_pct']}%** no buy-in {worst['buyin']} — "
                f"considere concentrar volume nos buy-ins mais baixos por enquanto."
            )
        else:
            st.success("ROI relativamente estável entre os buy-ins jogados.")
    else:
        st.caption(
            f"Poucos torneios com resultado por buy-in (mínimo {MIN_SAMPLE} pra "
            "um ROI minimamente confiável) — registre mais resultados pra "
            "destravar o insight automático aqui."
        )

conn.close()
