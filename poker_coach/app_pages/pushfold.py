"""Dashboard Push/Fold: aplica o solver de Nash (poker_coach.pushfold)
aos spots de abertura já importados, agrupa por faixa de stack (a
"tabela 15BB | spots=125 | acertou=109..." pedida) e mostra as piores
mãos com as cartas de verdade (não "Jc As" cru).
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import stats  # noqa: E402
from poker_coach.ui import cards, common, range_grid  # noqa: E402

common.page_title("Push/Fold", "🎯")
st.caption(
    "Escopo: só spots onde você foi o PRIMEIRO a agir voluntariamente no pote "
    "(ninguém tinha entrado ainda). Vilão modelado = a BB. Chip EV, não ICM. "
    "Confiável perto do botão (BTN/CO/HJ/SB); nos spots de UTG/MP trate como "
    "teto otimista — no jogo real tem mais gente pra pagar atrás, não só a BB."
)

conn = common.require_conn()

bb_min, bb_max = st.slider("Faixa de stack efetivo (BB) analisada", 1, 50, (5, 25))

if st.button("Rodar solver Nash", type="primary"):
    from poker_coach.pushfold import analyze as pf

    prog = st.progress(0.0, text="Resolvendo...")

    def _progress(i, total):
        if total:
            prog.progress(min(i / total, 1.0), text=f"Resolvendo... {i}/{total}")

    rows = pf.analyze_all(conn, bb_min=bb_min, bb_max=bb_max, progress=_progress)
    prog.empty()
    st.session_state["pf_rows"] = rows

rows = st.session_state.get("pf_rows")

if not rows:
    st.caption("Clique em **Rodar solver Nash** pra analisar os spots de abertura importados.")
else:
    from poker_coach.pushfold import analyze as pf

    s = pf.summarize(rows)
    c1, c2, c3 = st.columns(3)
    c1.metric("Spots analisados", s["spots"])
    c2.metric("Decisões erradas", s["leak_spots"])
    c3.metric("EV perdido total", f"{s['total_ev_lost_bb']:+.1f} BB")

    st.divider()
    st.subheader("Grid de range (13×13)")
    st.caption(
        "Verde = push +EV, vermelho = -EV, contra a range de call de "
        "equilíbrio da BB nesse stack/pot. Mesma leitura do ICMizer/HRC."
    )
    gc1, gc2 = st.columns(2)
    grid_eff_bb = gc1.slider("Stack efetivo (BB)", 1.0, 50.0, 10.0, 0.5, key="grid_eff_bb")
    grid_pot_bb = gc2.slider("Pot antes do push (BB)", 0.5, 10.0, 1.5, 0.25, key="grid_pot_bb")
    from poker_coach.pushfold import nash as pfnash
    ev_grid_data, grid_result = pfnash.ev_grid(grid_eff_bb, grid_pot_bb)
    st.markdown(
        f"**Push: {grid_result.shove_pct:.1f}%** das combinações "
        f"({len(grid_result.shove_classes)} classes) &nbsp;·&nbsp; "
        f"**Call da BB: {grid_result.call_pct:.1f}%**"
    )
    st.markdown(range_grid.range_grid_html(ev_grid_data), unsafe_allow_html=True)

    st.divider()
    st.subheader("Precisão por faixa de stack")
    buckets = [(0, 5), (5, 10), (10, 15), (15, 20), (20, 25), (25, 999)]
    bucket_rows = []
    for lo, hi in buckets:
        in_bucket = [r for r in rows if lo <= r.effective_bb < hi]
        if not in_bucket:
            continue
        correct = sum(1 for r in in_bucket if r.ev_lost_bb == 0)
        wrong = len(in_bucket) - correct
        label = f"{lo}-{hi}BB" if hi < 999 else f"{lo}+BB"
        bucket_rows.append({
            "faixa": label, "spots": len(in_bucket),
            "acertou": correct, "errou": wrong,
            "precisão": f"{correct / len(in_bucket) * 100:.0f}%",
            "EV perdido (BB)": round(sum(r.ev_lost_bb for r in in_bucket), 1),
        })
    if bucket_rows:
        st.dataframe(pd.DataFrame(bucket_rows), width='stretch', hide_index=True)

    st.divider()
    st.subheader("EV perdido por posição")
    pos_df = pd.DataFrame([{"posição": k, **v} for k, v in s["by_position"].items()])
    if not pos_df.empty:
        pos_df = pos_df.sort_values("ev_lost_bb", ascending=False)
        st.dataframe(pos_df.rename(columns={
            "spots": "spots", "leaks": "decisões erradas", "ev_lost_bb": "EV perdido (BB)"
        }), width='stretch', hide_index=True)
        st.bar_chart(pos_df.set_index("posição")["ev_lost_bb"])

    st.divider()
    st.subheader("Piores mãos (mais EV deixado na mesa)")
    worst = s["worst"]
    if not worst:
        st.caption("Nenhuma decisão errada encontrada nessa faixa — bom sinal.")
    else:
        table_rows = [{
            "torneio": r.tournament_id, "posição": r.position, "cartas": r.hero_cards,
            "stack ef. (BB)": r.effective_bb, "você fez": r.hero_decision,
            "Nash diz": r.nash_decision, "EV do push (BB)": f"{r.ev_push_bb:+.2f}",
            "EV perdido (BB)": f"{r.ev_lost_bb:.2f}",
        } for r in worst]
        html_table = cards.render_table(
            table_rows,
            columns=[("torneio", "Torneio"), ("posição", "Posição"), ("cartas", "Cartas"),
                     ("stack ef. (BB)", "Stack ef."), ("você fez", "Você fez"),
                     ("Nash diz", "Nash diz"), ("EV do push (BB)", "EV do push"),
                     ("EV perdido (BB)", "EV perdido")],
            card_columns={"cartas"},
        )
        st.markdown(html_table, unsafe_allow_html=True)

st.divider()
st.subheader("Leak bruto: fold/shove/raise por posição (sem o solver)")
bb_min2, bb_max2 = st.slider("Faixa de stack (BB) — leak bruto", 1, 60, (8, 20), key="leak_slider")
rep = stats.shortstack_fold_report(conn, bb_min2, bb_max2)
if rep:
    rdf = pd.DataFrame(rep).rename(columns={
        "position": "posição", "spots": "spots", "fold_pct": "fold %",
        "shove_pct": "shove %", "raise_pct": "raise %",
        "unopened_fold_pct": "fold em pote aberto %"})
    st.dataframe(rdf, width='stretch', hide_index=True)
    st.bar_chart(rdf.set_index("posição")[["fold %", "shove %", "raise %"]])
else:
    st.caption("Sem mãos nessa faixa de stack.")

conn.close()
