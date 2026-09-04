"""Dashboard de ICM (Malmuth-Harville).

Limitação FUNDAMENTAL, não escondida: ICM precisa dos stacks de TODOS
os jogadores restantes no torneio + a estrutura de premiação. A hand
history só mostra sua mesa — nunca o campo inteiro (um MTT tem várias
mesas). Essa análise só é válida quando a mesa da mão JÁ É a mesa final.
Por isso: você confirma explicitamente + informa a premiação antes de
qualquer número aparecer. Sem isso, o número seria inventado.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm, icm_analyze as ia  # noqa: E402
from poker_coach.ui import common  # noqa: E402

common.page_title("ICM", "🀄")

conn = common.require_conn()

st.warning(
    "Só calcula com sua confirmação explícita: a hand history nunca mostra "
    "o campo inteiro do torneio (só sua mesa), então isso só vale a pena "
    "perto/na mesa final, onde \"jogadores da mesa\" ≈ \"jogadores do "
    "torneio\". Motor: Malmuth-Harville (padrão da indústria pra "
    "push/fold leve — enviesa em campos muito grandes/díspares)."
)

st.subheader("1. Escolha o torneio e a premiação")
tournaments = conn.execute(
    """SELECT site, tournament_id, name, buyin FROM tournaments
       WHERE tournament_id IN (SELECT DISTINCT tournament_id FROM hands)
       ORDER BY first_seen DESC"""
).fetchall()
if not tournaments:
    st.info("Nenhum torneio importado ainda.")
    st.stop()

labels = [f"[{s}] {tid} — {name or '(sem nome)'} (buy-in {b})" for s, tid, name, b in tournaments]
idx = st.selectbox("Torneio", range(len(tournaments)), format_func=lambda i: labels[i], key="icm_tourney_sel")
site, tid, name, buyin = tournaments[idx]

existing = dbm.get_payouts(conn, site, tid)
st.caption(
    "Premiação por lugar (1º, 2º, 3º...), separada por vírgula, em $. "
    "Vem do lobby/histórico do site — a hand history não traz isso."
)
payout_text = st.text_input(
    "Premiação (1º,2º,3º,...)",
    value=", ".join(str(p) for p in existing) if existing else "",
    placeholder="ex.: 10.71, 6.00, 3.00",
    key="icm_payout_text",
)
if st.button("💾 Salvar premiação", key="icm_save_payout"):
    try:
        prizes = [float(p.strip()) for p in payout_text.split(",") if p.strip()]
    except ValueError:
        st.error("Não consegui ler os valores — use números separados por vírgula.")
    else:
        dbm.set_payouts(conn, site, tid, prizes)
        conn.commit()
        st.success(f"Premiação salva: {prizes}")
        st.rerun()

payouts = dbm.get_payouts(conn, site, tid)
if not payouts:
    st.info("Salve a premiação acima pra continuar.")
    conn.close()
    st.stop()

st.divider()
st.subheader("2. Confirme o escopo")
max_table = st.slider(
    "Considerar só mãos com até quantos jogadores na mesa (proxy de \"mesa final\")",
    2, 9, 9, key="icm_max_table",
)
confirmed = st.checkbox(
    f"Confirmo que as mãos com até {max_table} jogadores nesse torneio "
    "já eram a mesa final (ou o torneio inteiro era desse tamanho).",
    key="icm_confirm",
)
if not confirmed:
    st.caption("Marque a confirmação acima pra rodar a análise.")
    conn.close()
    st.stop()

st.divider()
st.subheader("3. Resultado")
if st.button("Rodar ICM", type="primary", key="icm_run"):
    rows = ia.analyze_icm_tournament(conn, site, tid, payouts, max_table_size=max_table)
    st.session_state["icm_rows"] = rows

rows = st.session_state.get("icm_rows")
if not rows:
    st.caption("Clique em **Rodar ICM** pra analisar.")
    conn.close()
    st.stop()

s = ia.summarize_icm(rows)
c1, c2, c3 = st.columns(3)
c1.metric("Spots encontrados", s["spots"])
c2.metric("Decisões erradas (ICM)", s["leak_spots"])
c3.metric("EV perdido/ganho total ($)", f"{s['total_ev_lost']:+.2f}")

st.caption(
    "Risk Premium: quanto sua sobrevivência vale a mais em $ do que sua "
    "fatia de fichas sugere, naquele momento — positivo = jogue mais "
    "tight que chip EV manda; negativo = seu stack curto ganha "
    "desproporcionalmente empurrando (comum perto da bolha)."
)

table_rows = [{
    "hand_id": r.hand_id, "data": r.ts, "posição": r.position, "cartas": r.hero_cards,
    "stack (BB)": r.effective_bb, "jogadores": r.n_players,
    "você fez": r.hero_decision, "ICM diz": r.icm_decision,
    "EV fold ($)": r.icm_ev_fold, "EV push ($)": r.icm_ev_push,
    "EV perdido ($)": r.icm_ev_lost, "risk premium %": r.risk_premium_pct,
} for r in rows]
by_hand_id = {r.hand_id: r for r in rows}
df = pd.DataFrame(table_rows).sort_values("EV perdido ($)", ascending=False).reset_index(drop=True)

event = st.dataframe(
    df.drop(columns=["hand_id"]), width='stretch', hide_index=True,
    on_select="rerun", selection_mode="single-row",
)

if event.selection.rows:
    picked_row = by_hand_id[df.iloc[event.selection.rows[0]]["hand_id"]]
    if st.button(f"▶ Abrir mão {picked_row.hand_id} no Replayer"):
        st.session_state["rp_hand"] = (picked_row.site, picked_row.hand_id)
        st.session_state["rp_step"] = 0
        st.switch_page("app_pages/replayer.py")

conn.close()
