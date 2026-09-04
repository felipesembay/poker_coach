"""Estado compartilhado entre as páginas do dashboard: DSN do Postgres
(escolhido na página de Configuração, persistido em st.session_state pra
todas as outras páginas usarem) e conexão.

IMPORTANTE: usa poker_coach.db.connect() (não psycopg2.connect() cru) —
esse é o único jeito de garantir que tabelas novas adicionadas depois
que o banco já existia (migração via ALTER TABLE / CREATE TABLE IF NOT
EXISTS) fiquem presentes mesmo abrindo o banco só pra leitura numa
página. Sem isso, uma tabela adicionada ao schema só aparece pra quem
importar uma hand history de novo — todas as outras páginas quebrariam
com "no such table" (já aconteceu durante o desenvolvimento, com SQLite)."""
import streamlit as st

from .. import db as _dbm

DEFAULT_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach"


def get_db_path() -> str:
    return st.session_state.get("db_path", DEFAULT_DSN)


def set_db_path(path: str) -> None:
    st.session_state["db_path"] = path


def get_conn() -> _dbm.PGConnection | None:
    dsn = get_db_path()
    try:
        return _dbm.connect(dsn)
    except Exception as e:  # conexão recusada, DSN inválido, banco fora do ar etc.
        st.session_state["_db_conn_error"] = str(e)
        return None


def require_conn() -> _dbm.PGConnection:
    """Pra páginas que não fazem sentido sem banco: mostra aviso + para."""
    conn = get_conn()
    if conn is None:
        err = st.session_state.get("_db_conn_error", "")
        st.info(
            f"Não consegui conectar em `{get_db_path()}`. Vá em "
            "**⚙️ Configuração e Importação** pra ajustar a conexão."
        )
        if err:
            st.caption(f"Erro: {err}")
        st.stop()
    return conn


def configure_app() -> None:
    """Chamar UMA VEZ no script roteador (streamlit_app.py), antes de
    st.navigation(...).run() — st.set_page_config só pode rodar uma vez
    por execução, então as páginas individuais não chamam isso."""
    st.set_page_config(page_title="Poker Lab", page_icon="🃏", layout="wide")


def page_title(title: str, icon: str = "") -> None:
    """Título da página em si (o nome na barra lateral vem do st.Page,
    definido no roteador — são duas coisas independentes)."""
    st.title(f"{icon} {title}".strip())
