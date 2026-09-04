"""Configuração do banco, importação de hand histories e registro de
resultado de torneio (posição final + prêmio, dinheiro ou ticket) —
sem isso, nenhum dashboard de $ (Lucro, ROI, ITM, ABI) tem o que mostrar.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm, stats  # noqa: E402
from poker_coach.ui import common  # noqa: E402


def _try_connect(dsn: str):
    try:
        return dbm.connect(dsn)
    except Exception as e:
        return e


common.page_title("Configuração e Importação", "⚙️")

st.subheader("Banco de dados (PostgreSQL)")
db_path = st.text_input("Connection string", value=common.get_db_path(),
                         help="postgresql://usuário:senha@host:porta/banco")
common.set_db_path(db_path)
_probe = _try_connect(db_path)
if isinstance(_probe, Exception):
    st.warning(f"Não conectei em `{db_path}`: {_probe}")
else:
    st.success(f"Conectado a `{db_path}`.")
    _probe.close()

st.divider()
st.subheader("Importar hand histories")
uploaded = st.file_uploader("Arquivos .txt (PartyPoker / PokerStars)", type=["txt"],
                             accept_multiple_files=True)
if uploaded and st.button("Importar"):
    from poker_coach.cli import detect_site
    from poker_coach.parsers import partypoker, pokerstars

    conn = dbm.connect(db_path)
    total_new = 0
    for f in uploaded:
        text = f.read().decode("utf-8", errors="replace")
        site = detect_site(text)
        if site is None:
            st.error(f"{f.name}: formato não reconhecido.")
            continue
        parser = pokerstars if site == "pokerstars" else partypoker
        hands = parser.parse_file(text)
        new = sum(dbm.insert_hand(conn, h) for h in hands)
        total_new += new
        st.write(f"**{f.name}** ({site}): {len(hands)} mãos no arquivo, {new} novas.")
    conn.commit()
    conn.close()
    st.success(f"{total_new} mãos novas importadas no total.")
    st.rerun()

st.divider()
st.subheader("Registrar resultado de torneio")
st.caption(
    "A hand history não contém sua posição final nem o prêmio — sem "
    "registrar isso aqui, os dashboards de Lucro/ROI/ITM/ABI ficam vazios. "
    "Se o prêmio foi um **bilhete de satélite** (não dinheiro), marque "
    "\"Ticket\" — o Sharkscope não distingue isso, mas aqui dá pra acompanhar."
)
conn = None if isinstance(_probe, Exception) else dbm.connect(db_path)
if conn is None:
    st.caption("Corrija a connection string acima primeiro.")
else:
    pending = stats.results_pending(conn)
    if not pending:
        st.success("Todos os torneios importados já têm resultado registrado.")
    else:
        labels = [
            f"[{site}] {tid} | buy-in {buyin} {currency or ''} | {hands} mãos | desde {first}"
            for site, tid, buyin, currency, hands, first in pending
        ]
        idx = st.selectbox("Torneio", range(len(pending)), format_func=lambda i: labels[i])
        site, tid, buyin, currency, _hands, _first = pending[idx]

        c1, c2 = st.columns(2)
        position = c1.number_input("Posição final", min_value=1, step=1, value=1)
        prize_type = c2.radio("Prêmio em", ["Dinheiro", "Ticket"], horizontal=True)

        if prize_type == "Dinheiro":
            prize = st.number_input("Prêmio recebido ($)", min_value=0.0, step=0.01, value=0.0)
            note = None
        else:
            c3, c4 = st.columns(2)
            prize = c3.number_input("Valor estimado do ticket ($)", min_value=0.0,
                                     step=0.01, value=float(buyin or 0))
            note = c4.text_input("Descrição do ticket", placeholder="ex.: Ticket Sunday $11")

        if st.button("Salvar resultado"):
            dbm.set_result(conn, site, tid, int(position), float(prize),
                            prize_type="cash" if prize_type == "Dinheiro" else "ticket",
                            prize_note=note)
            conn.commit()
            st.success(f"Resultado salvo: [{site}] {tid} → {position}º, "
                       f"{prize_type.lower()} {prize:.2f}.")
            st.rerun()

    sat = stats.satellite_history(conn)
    if sat:
        st.divider()
        conv = stats.satellite_conversion_rate(conn)
        st.subheader(f"🎟️ Seus satélites ({conv['converted']}/{conv['attempts']} "
                     f"converteram — {conv['pct']}%)")
        import pandas as pd
        st.dataframe(pd.DataFrame(sat), width='stretch', hide_index=True)

    conn.close()
