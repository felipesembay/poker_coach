"""Grid 13x13 de range (estilo ICMizer/HRC): cada célula é uma classe de
mão, colorida por EV do push (verde = +EV, vermelho = -EV), como o
gráfico de spots que faltava na página de Push/Fold.
"""
import html

RANKS_DESC = "AKQJT98765432"


def class_at(row: int, col: int) -> str:
    if row == col:
        return RANKS_DESC[row] * 2
    if row < col:
        return RANKS_DESC[row] + RANKS_DESC[col] + "s"
    return RANKS_DESC[col] + RANKS_DESC[row] + "o"


def _color(ev: float, vmax: float) -> tuple[str, str]:
    """(background, texto) — verde escala com EV positivo, vermelho com negativo."""
    if vmax <= 0:
        vmax = 1.0
    t = min(abs(ev) / vmax, 1.0)
    if ev >= 0:
        # branco-esverdeado -> verde forte
        r = round(214 - t * 190)
        g = round(238 - t * 88)
        b = round(214 - t * 190)
    else:
        r = round(238 - t * 8)
        g = round(214 - t * 150)
        b = round(214 - t * 150)
    bg = f"rgb({r},{g},{b})"
    text = "#0a0a0a" if t < 0.55 else "#ffffff"
    return bg, text


def range_grid_html(ev_grid: dict[str, float], cell_px: int = 42) -> str:
    values = list(ev_grid.values())
    vmax = max((abs(v) for v in values), default=1.0)

    rows_html = []
    for r in range(13):
        cells = []
        for c in range(13):
            cls = class_at(r, c)
            ev = ev_grid.get(cls, 0.0)
            bg, text = _color(ev, vmax)
            cells.append(
                f'<div style="width:{cell_px}px;height:{cell_px}px;background:{bg};'
                f'color:{text};display:flex;flex-direction:column;align-items:center;'
                f'justify-content:center;font-family:Arial,sans-serif;'
                f'font-size:{cell_px * 0.24:.0f}px;border:1px solid rgba(0,0,0,.15);'
                f'box-sizing:border-box;line-height:1.1;">'
                f'<span style="font-weight:700;">{html.escape(cls)}</span>'
                f'<span style="font-size:{cell_px * 0.20:.0f}px;">{ev:+.2f}</span></div>'
            )
        rows_html.append('<div style="display:flex;">' + "".join(cells) + "</div>")

    return '<div style="display:inline-block;border:2px solid #333;">' + "".join(rows_html) + "</div>"
