"""Poker Lab — roteador. Define a navegação (com seções agrupadas na
barra lateral) e delega o conteúdo pra app_pages/*.py. Não colocar
lógica de página aqui — só roteamento.
"""
import streamlit as st

from poker_coach.ui import common

common.configure_app()

pages = {
    "": [
        st.Page("app_pages/config.py", title="Configuração e Importação", icon="⚙️"),
    ],
    "Dashboard": [
        st.Page("app_pages/home.py", title="Geral", icon="🏠", default=True),
        st.Page("app_pages/lucro.py", title="Lucro", icon="💰"),
        st.Page("app_pages/roi.py", title="ROI", icon="📈"),
        st.Page("app_pages/pushfold.py", title="Push/Fold", icon="🎯"),
        st.Page("app_pages/posicao.py", title="Posição", icon="📍"),
        st.Page("app_pages/stack.py", title="Stack", icon="📊"),
        st.Page("app_pages/icm.py", title="ICM", icon="🀄"),
    ],
    "Replayer": [
        st.Page("app_pages/replayer.py", title="Replayer", icon="🔁"),
        st.Page("app_pages/modo_estudo.py", title="Modo Estudo", icon="🎓"),
        st.Page("app_pages/evolucao.py", title="Evolução", icon="📅"),
    ],
}

nav = st.navigation(pages)
nav.run()
