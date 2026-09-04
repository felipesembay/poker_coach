"""Renderização de cartas como HTML (mini-cards estilo baralho real:
fundo branco fixo, texto vermelho/preto — assim funciona igual no tema
claro e escuro do Streamlit, sem depender de CSS de tema).

st.dataframe não permite HTML por célula, então onde as cartas aparecem
numa tabela, montamos a tabela inteira como HTML via st.markdown
(ver render_table abaixo) em vez de usar st.dataframe.
"""
import html

SUIT_SYMBOL = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
SUIT_COLOR = {"s": "#1a1a1a", "c": "#1a1a1a", "h": "#c81e3a", "d": "#c81e3a"}


def _parse_cards(cards_str: str) -> list[str]:
    if not cards_str:
        return []
    # só tokens "Rs" válidos (rank+naipe, 2 chars) — protege contra
    # placeholders tipo "?" acabando aqui por engano.
    return [c for c in cards_str.replace(",", " ").split() if len(c) == 2]


def card_html(card: str, w: int = 32, h: int = 44) -> str:
    rank, suit = card[0].upper(), card[1].lower()
    disp_rank = "10" if rank == "T" else rank
    color = SUIT_COLOR.get(suit, "#1a1a1a")
    symbol = SUIT_SYMBOL.get(suit, "?")
    return (
        f'<span style="display:inline-flex;flex-direction:column;align-items:center;'
        f'justify-content:center;width:{w}px;height:{h}px;border-radius:6px;'
        f'background:#fdfdfd;border:1px solid #999;margin-right:3px;'
        f'font-family:Georgia,\'Times New Roman\',serif;color:{color};'
        f'box-shadow:0 1px 2px rgba(0,0,0,.35);vertical-align:middle;">'
        f'<span style="font-size:{h * 0.32:.0f}px;font-weight:700;line-height:1.1;">{disp_rank}</span>'
        f'<span style="font-size:{h * 0.30:.0f}px;line-height:1;">{symbol}</span></span>'
    )


def hand_html(cards_str: str, w: int = 32, h: int = 44) -> str:
    """'Jc As' -> duas mini-cartas HTML lado a lado."""
    return "".join(card_html(c, w, h) for c in _parse_cards(cards_str))


def board_html(board_str: str, w: int = 28, h: int = 38) -> str:
    return "".join(card_html(c, w, h) for c in _parse_cards(board_str))


def render_table(rows: list[dict], columns: list[tuple[str, str]],
                  card_columns: set[str] = frozenset()) -> str:
    """Monta uma tabela HTML simples, tema-compatível (usa variáveis CSS do
    Streamlit) — `columns` é [(chave, título)], `card_columns` marca quais
    chaves devem ser renderizadas como mini-cartas em vez de texto puro."""
    head = "".join(f"<th style='text-align:left;padding:6px 10px;"
                    f"border-bottom:2px solid rgba(128,128,128,.4);'>{html.escape(title)}</th>"
                    for _, title in columns)
    body_rows = []
    for row in rows:
        cells = []
        for key, _ in columns:
            val = row.get(key, "")
            if key in card_columns:
                cell = hand_html(str(val)) if val else ""
            else:
                cell = html.escape(str(val))
            cells.append(f"<td style='padding:6px 10px;border-bottom:1px solid rgba(128,128,128,.15);"
                         f"white-space:nowrap;'>{cell}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<div style='overflow-x:auto;'><table style='border-collapse:collapse;width:100%;'>"
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>"
    )
