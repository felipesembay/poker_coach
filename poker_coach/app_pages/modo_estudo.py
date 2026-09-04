"""Modo Estudo: esconde sua decisão real, mostra só cartas/stack/posição,
você responde Fold ou Push (All-in) — só essas duas, porque é só isso
que o motor de Nash julga nesses spots (ver poker_coach/pushfold). Sem
fingir avaliar Call/Raise de tamanho variável sem um motor que saiba
julgar essas linhas.

Escopo idêntico ao Push/Fold: só spots de abertura (ninguém entrou antes
do herói), vilão modelado = BB.
"""
import random
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm  # noqa: E402
from poker_coach.ui import cards, common  # noqa: E402

common.page_title("Modo Estudo", "🎓")
st.caption(
    "A plataforma esconde o que você realmente fez na mão. Você decide "
    "Fold ou Push com o que um jogador real teria na hora: cartas, stack, "
    "posição. Depois mostra se bateu com o Nash e quanto EV isso valeu."
)

conn = common.require_conn()

qs = dbm.quiz_stats(conn)
c1, c2 = st.columns(2)
c1.metric("Acurácia no Modo Estudo (histórico)", f"{qs['pct']}%" if qs["pct"] is not None else "—")
c2.metric("Perguntas respondidas", qs["total"])


def _pick_hand():
    """precise=False (matriz pré-computada, sem Monte Carlo ao vivo) —
    o mesmo caminho rápido do relatório em lote. precise=True aqui
    dentro do loop de busca era o motivo da demora (~30s): cada
    candidato fora do escopo é descartado rápido, mas o candidato QUE
    ACERTA rodava até ~100 mil simulações de mão pra 1 EV só."""
    from poker_coach.pushfold import analyze as pf

    candidates = conn.execute(
        """SELECT site, hand_id FROM hands
           WHERE hero_position IS NOT NULL AND hero_position != 'BB'
             AND hero_stack_bb BETWEEN 5 AND 25
           ORDER BY RANDOM() LIMIT 60"""
    ).fetchall()
    for site, hand_id in candidates:
        row = pf.analyze_hand_row(conn, site, hand_id, precise=False)
        if row is not None:
            return row
    return None


if "quiz_row" not in st.session_state or st.button("🔀 Nova mão"):
    row = _pick_hand()
    st.session_state["quiz_row"] = row
    st.session_state["quiz_answered"] = False

row = st.session_state.get("quiz_row")
if row is None:
    st.warning(
        "Não achei nenhum spot de abertura na faixa de 5-25 BB pra sortear. "
        "Importe mais mãos ou tente de novo."
    )
    st.stop()

st.divider()
st.markdown(
    f"### Você — {row.effective_bb}BB — {row.position}<br>"
    + cards.hand_html(row.hero_cards, w=50, h=68),
    unsafe_allow_html=True,
)
st.caption(f"Pot antes da sua decisão: {row.pot_bb} BB. Ninguém entrou ainda. O que você faz?")

if not st.session_state.get("quiz_answered"):
    b1, b2 = st.columns(2)
    if b1.button("🔴 Fold", type="secondary", key="quiz_fold"):
        st.session_state["quiz_answer"] = "fold"
        st.session_state["quiz_answered"] = True
        st.rerun()
    if b2.button("🟢 Push (All-in)", type="primary", key="quiz_push"):
        st.session_state["quiz_answer"] = "push"
        st.session_state["quiz_answered"] = True
        st.rerun()
else:
    answer = st.session_state["quiz_answer"]
    correct = answer == row.nash_decision
    st.markdown(f"**Sua decisão:** {answer}")
    st.markdown(f"**Nash:** {row.nash_decision}")
    quiz_ev_lost = 0.0
    if correct:
        st.success(f"✅ Correto! EV do push nesse spot: {row.ev_push_bb:+.2f} BB")
    else:
        quiz_ev_lost = abs(row.ev_push_bb if row.nash_decision == "push" else -row.ev_push_bb)
        st.error(f"❌ Errado. EV perdido: {quiz_ev_lost:.2f} BB "
                 f"(EV do push era {row.ev_push_bb:+.2f} BB)")

    if not st.session_state.get("quiz_logged"):
        # EV perdido é da RESPOSTA DO QUIZ, não da decisão real que o
        # herói tomou na mão de verdade (row.ev_lost_bb) — podem ser
        # diferentes se você responder diferente do que fez ao vivo.
        dbm.log_quiz_answer(conn, row.site, row.hand_id, answer, row.nash_decision, quiz_ev_lost)
        conn.commit()
        st.session_state["quiz_logged"] = True

    if st.button("Próxima mão ▶", type="primary"):
        new_row = _pick_hand()
        st.session_state["quiz_row"] = new_row
        st.session_state["quiz_answered"] = False
        st.session_state["quiz_logged"] = False
        st.rerun()

conn.close()
