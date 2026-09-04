"""Replayer: busca de mãos + reconstrução completa (mesa, stacks, pot,
board, ações passo a passo) + Painel IA (reusa o motor de Push/Fold) +
notas/tags/favorito.

Limitações assumidas e comunicadas na tela, não escondidas:
- Árvore de decisão com branches alternativos (Raise -> Fold/Call/3Bet)
  não existe: a hand history só grava a linha que realmente aconteceu.
  O que dá pra mostrar é a sequência real de ações (isso está aqui).
- Painel IA só dá recomendação pros spots que o motor de Push/Fold cobre
  (abertura preflop, sem ninguém ter entrado antes). Fora disso, mostra
  que não há motor pra aquele tipo de spot ainda (pós-flop, 3bet, ICM).
- Equity: só quando o vilão pagou e mostrou as cartas (showdown real) ou
  quando o spot está no escopo do Push/Fold (equity vs a range de call
  de equilíbrio). Sem isso, não inventa número.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm, replay  # noqa: E402
from poker_coach.ui import cards, common, table  # noqa: E402

common.page_title("Replayer", "🔁")

conn = common.require_conn()

# ---------------- Busca ----------------
with st.expander("🔎 Buscar mãos", expanded="rp_hand" not in st.session_state):
    c1, c2, c3 = st.columns(3)
    positions = [r[0] for r in conn.execute(
        "SELECT DISTINCT hero_position FROM hands WHERE hero_position IS NOT NULL")]
    pos_sel = c1.selectbox("Posição", ["(todas)"] + sorted(positions))
    bb_range = c2.slider("Stack (BB)", 0, 60, (0, 60))
    tags_available = ["(todas)"] + dbm.SUGGESTED_TAGS + [
        t for t in dbm.all_tags_used(conn) if t not in dbm.SUGGESTED_TAGS]
    tag_sel = c3.selectbox("Tag", tags_available)
    c4, c5 = st.columns(2)
    fav_only = c4.checkbox("Só favoritas ★", key="search_fav_only")
    sd_only = c5.checkbox("Só com showdown (cartas do vilão conhecidas)", key="search_sd_only")

    results = replay.list_hands(
        conn,
        position=None if pos_sel == "(todas)" else pos_sel,
        bb_min=bb_range[0], bb_max=bb_range[1],
        tag=None if tag_sel == "(todas)" else tag_sel,
        favorite=True if fav_only else None,
        showdown=True if sd_only else None, limit=100,
    )
    st.caption(f"{len(results)} mãos encontradas (mostrando até 100).")
    if results:
        rows_html = [{
            "quando": r["ts"] or "", "posição": r["position"] or "", "cartas": r["hero_cards"] or "",
            "stack (BB)": r["stack_bb"], "saldo (BB)": r["net_bb"], "★": "★" if r["favorite"] else "",
            "_key": f"{r['site']}|{r['hand_id']}",
        } for r in results]
        st.markdown(cards.render_table(
            rows_html,
            columns=[("quando", "Quando"), ("posição", "Posição"), ("cartas", "Cartas"),
                     ("stack (BB)", "Stack"), ("saldo (BB)", "Saldo"), ("★", "★")],
            card_columns={"cartas"},
        ), unsafe_allow_html=True)
        labels = [f"{r['ts']} | {r['position']} | {r['hero_cards']} | {r['stack_bb']}BB" for r in results]
        idx = st.selectbox("Abrir mão", range(len(results)), format_func=lambda i: labels[i])
        if st.button("▶ Abrir no Replayer", type="primary"):
            st.session_state["rp_hand"] = (results[idx]["site"], results[idx]["hand_id"])
            st.session_state["rp_step"] = 0
            st.rerun()

# ---------------- Replay ----------------
sel = st.session_state.get("rp_hand")
if not sel:
    st.info("Busque e abra uma mão acima pra começar.")
    st.stop()

site, hand_id = sel
rh = replay.load(conn, site, hand_id)
if rh is None:
    st.error("Mão não encontrada (banco pode ter mudado).")
    st.stop()

st.divider()
st.subheader(f"Mão {hand_id} — torneio {rh.tournament_id}")

step_idx = st.session_state.get("rp_step", 0)
n = len(rh.steps)

nav = st.columns(5)
if nav[0].button("⏮ Início"):
    step_idx = -1
if nav[1].button("◀ Anterior") and step_idx > -1:
    step_idx -= 1
if nav[2].button("Próxima ▶") and step_idx < n - 1:
    step_idx += 1
if nav[3].button("Fim ⏭"):
    step_idx = n - 1
nav[4].caption(f"Passo {step_idx + 1}/{n}" if step_idx >= 0 else "Antes de qualquer ação")
st.session_state["rp_step"] = step_idx

# timeline por rua — clique pula direto
street_labels = {"preflop": "Preflop", "flop": "Flop", "turn": "Turn", "river": "River"}
tl_cols = st.columns(len(rh.street_first_index) or 1)
for i, (street, first_idx) in enumerate(rh.street_first_index.items()):
    if tl_cols[i].button(street_labels.get(street, street), key=f"tl_{street}"):
        st.session_state["rp_step"] = first_idx
        st.rerun()

pot, stacks, board_so_far = rh.state_at(step_idx)

st.markdown(f"**Blinds:** {rh.sb}/{rh.bb} (ante {rh.ante})", unsafe_allow_html=True)

# ---------------- Mesa (SVG) ----------------
folded_so_far = {s.player for s in rh.steps[:step_idx + 1] if s.action == "fold"}
acting = rh.steps[step_idx].player if step_idx >= 0 else None
st.markdown(table.poker_table_svg(
    seat_order=rh.seat_order, positions=rh.positions, hero=rh.hero,
    stacks=stacks, starting_stacks=rh.starting_stacks(),
    hero_cards=rh.hero_cards, shown_cards=rh.shown_cards,
    pot=pot, board_so_far=board_so_far, bb=rh.bb,
    folded=folded_so_far, acting_player=acting,
), unsafe_allow_html=True)

# ---------------- Ações por rua ----------------
st.markdown("#### Ações")
current_street = rh.steps[step_idx].street if step_idx >= 0 else "preflop"
for street in ["preflop", "flop", "turn", "river"]:
    street_steps = [s for s in rh.steps if s.street == street and s.action != "resolve"]
    if not street_steps:
        continue
    st.markdown(f"**{street_labels[street]}**")
    lines = []
    for s in street_steps:
        idx_in_all = rh.steps.index(s)
        marker = "👉 " if idx_in_all == step_idx else "&nbsp;&nbsp;&nbsp;"
        label = f"{s.position or s.player} {s.action}" + (f" {s.amount}" if s.amount else "")
        if idx_in_all > step_idx:
            label = f"<span style='opacity:.35'>{label}</span>"
        lines.append(f"{marker}{label}")
    st.markdown("<br>".join(lines), unsafe_allow_html=True)

st.divider()

# ---------------- Painel IA + estatísticas ----------------
left, right = st.columns([3, 2])

with right:
    st.markdown("### 🤖 Painel IA")
    from poker_coach.pushfold import analyze as pf
    ia_row = pf.analyze_hand_row(conn, site, hand_id, precise=True)
    if ia_row is None:
        st.caption(
            "Fora do escopo do motor atual (só cobre a decisão de ABRIR o pote "
            "preflop, primeiro a agir). Sem motor pós-flop/ICM/3bet ainda."
        )
    else:
        st.markdown(f"**Hero:** {ia_row.hero_cards} · {ia_row.effective_bb}BB · {ia_row.position}")
        rec = "🟢 Empurrar" if ia_row.nash_decision == "push" else "🔴 Foldar"
        did = "empurrou" if ia_row.hero_decision == "push" else "deu fold"
        st.markdown(f"**Nash recomenda:** {rec}")
        st.markdown(f"**Você:** {did}")
        color = "🟢" if ia_row.ev_lost_bb == 0 else "🔴"
        st.markdown(f"**{color} EV do push:** {ia_row.ev_push_bb:+.2f} BB")
        if ia_row.ev_lost_bb > 0:
            st.warning(f"EV perdido: {ia_row.ev_lost_bb:.2f} BB")
        else:
            st.success("Decisão bateu com o Nash.")

    st.markdown("### 📐 Estatísticas do passo atual")
    if step_idx >= 0 and rh.steps[step_idx].player == rh.hero:
        step = rh.steps[step_idx]
        pot_before, stacks_before, _ = rh.state_at(step_idx - 1)
        hero_stack_before = stacks_before.get(rh.hero, 0)
        spr = round(hero_stack_before / pot_before, 2) if pot_before else None
        st.metric("SPR (stack/pot antes da ação)", spr if spr is not None else "—")
        if step.action == "call" and step.amount:
            pot_odds = round(step.amount / (pot_before + step.amount) * 100, 1)
            st.metric("Pot odds (pagando)", f"{pot_odds}%")
        else:
            st.caption("Pot odds só calculado quando a ação é 'call' "
                       "(precisa do valor exato pago).")
    else:
        st.caption("Selecione um passo em que o herói age pra ver SPR/pot odds.")
    st.caption("ICM / Risk Premium: motor de ICM ainda não implementado (página 🀄 ICM).")

with left:
    st.markdown("### 📝 Notas e tags")
    note = st.text_area("Nota", value=dbm.get_note(conn, site, hand_id), height=100, key="note_text")
    fav = st.checkbox("★ Favoritar", value=bool(
        conn.execute("SELECT favorite FROM hands WHERE site=? AND hand_id=?",
                     (site, hand_id)).fetchone()[0]), key="fav_checkbox")
    current_tags = dbm.get_tags(conn, site, hand_id)
    tag_options = sorted(set(dbm.SUGGESTED_TAGS) | set(dbm.all_tags_used(conn)) | set(current_tags))
    new_tags = st.multiselect("Tags", tag_options, default=current_tags, key="tags_select")
    if st.button("💾 Salvar", key="save_note_btn"):
        dbm.set_note(conn, site, hand_id, note)
        dbm.set_favorite(conn, site, hand_id, fav)
        dbm.set_tags(conn, site, hand_id, new_tags)
        conn.commit()
        st.success("Salvo.")

conn.close()
