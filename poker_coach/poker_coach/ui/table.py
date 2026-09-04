"""Mesa de poker visual (SVG): oval verde, assentos distribuídos ao
redor, cartas, stacks, botão do dealer, pot e board no centro — como um
replayer de verdade, não uma lista de linhas.

SVG puro (sem <foreignObject>/HTML embutido) pra renderizar igual em
qualquer navegador dentro do iframe do Streamlit.
"""
import html
import math

SUIT_SYMBOL = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}


def _card_svg(card: str, x: float, y: float, w: float, h: float) -> str:
    rank, suit = card[0].upper(), card[1].lower()
    disp = "10" if rank == "T" else rank
    color = "#c81e3a" if suit in "hd" else "#161616"
    symbol = SUIT_SYMBOL.get(suit, "?")
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" '
        f'fill="#fdfdfd" stroke="#333" stroke-width="1"/>'
        f'<text x="{x + w / 2:.1f}" y="{y + h * 0.44:.1f}" text-anchor="middle" '
        f'font-size="{h * 0.34:.0f}" fill="{color}" font-family="Georgia,serif" '
        f'font-weight="700">{disp}</text>'
        f'<text x="{x + w / 2:.1f}" y="{y + h * 0.84:.1f}" text-anchor="middle" '
        f'font-size="{h * 0.32:.0f}" fill="{color}" font-family="Arial">{symbol}</text>'
    )


def _facedown_svg(x: float, y: float, w: float, h: float) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="4" '
        f'fill="#7f1d1d" stroke="#fff" stroke-width="1.2"/>'
        f'<rect x="{x + 3:.1f}" y="{y + 3:.1f}" width="{w - 6:.1f}" height="{h - 6:.1f}" '
        f'rx="2" fill="none" stroke="#c88" stroke-width="1" opacity="0.6"/>'
    )


def poker_table_svg(
    seat_order: list[str], positions: dict[str, str], hero: str | None,
    stacks: dict[str, int], starting_stacks: dict[str, int],
    hero_cards: str | None, shown_cards: dict[str, str],
    pot: int, board_so_far: str, bb: int, folded: set[str] | None = None,
    acting_player: str | None = None, width: int = 880, height: int = 560,
) -> str:
    folded = folded or set()
    n = len(seat_order)
    if n == 0:
        return "<p>Sem jogadores.</p>"

    if hero in seat_order:
        hi = seat_order.index(hero)
        ordered = seat_order[hi:] + seat_order[:hi]
    else:
        ordered = seat_order

    cx, cy = width / 2, height / 2 - 6
    table_rx, table_ry = width * 0.34, height * 0.26
    seat_rx, seat_ry = width * 0.43, height * 0.34
    box_w, box_h = 128, 58

    parts = [
        f'<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="max-width:100%;">',
        # feltro
        f'<ellipse cx="{cx}" cy="{cy}" rx="{table_rx}" ry="{table_ry}" '
        f'fill="#0b6b3a" stroke="#5a3a1a" stroke-width="16"/>',
        f'<ellipse cx="{cx}" cy="{cy}" rx="{table_rx - 12}" ry="{table_ry - 12}" '
        f'fill="none" stroke="#159a55" stroke-width="2" opacity="0.5"/>',
        f'<text x="{cx}" y="{cy - table_ry * 0.35}" text-anchor="middle" fill="white" '
        f'font-size="17" font-family="Arial" font-weight="bold">Pot: {pot:,}</text>',
    ]

    board_list = board_so_far.split() if board_so_far else []
    if board_list:
        cw, ch = 34, 46
        total_w = len(board_list) * (cw + 4)
        bx = cx - total_w / 2
        for i, card in enumerate(board_list):
            parts.append(_card_svg(card, bx + i * (cw + 4), cy - ch / 2, cw, ch))
    else:
        parts.append(f'<text x="{cx}" y="{cy + 6}" text-anchor="middle" fill="#bcd" '
                      f'font-size="13" font-family="Arial">(sem board ainda)</text>')

    start_angle = 90.0  # herói embaixo, centro
    for i, player in enumerate(ordered):
        angle = math.radians(start_angle + i * (360.0 / n))
        sx = cx + seat_rx * math.cos(angle)
        sy = cy + seat_ry * math.sin(angle)
        is_hero = player == hero
        is_folded = player in folded
        pos_label = positions.get(player, "")
        stack = stacks.get(player, starting_stacks.get(player, 0))
        stack_bb = round(stack / bb, 1) if bb else 0

        bx0, by0 = sx - box_w / 2, sy - box_h / 2
        border = "#f5c518" if is_hero else "#888"
        opacity = 0.45 if is_folded else 0.94
        parts.append(
            f'<rect x="{bx0:.1f}" y="{by0:.1f}" width="{box_w}" height="{box_h}" rx="8" '
            f'fill="#111827" stroke="{border}" stroke-width="{3 if is_hero else 1.5}" '
            f'opacity="{opacity}"/>'
        )
        parts.append(
            f'<text x="{sx:.1f}" y="{by0 + 15:.1f}" text-anchor="middle" fill="#f5c518" '
            f'font-size="11" font-family="Arial" font-weight="bold">{html.escape(pos_label)}'
            f'</text>'
        )
        name = player if len(player) <= 13 else player[:12] + "…"
        parts.append(
            f'<text x="{sx:.1f}" y="{by0 + 30:.1f}" text-anchor="middle" fill="white" '
            f'font-size="12" font-family="Arial">{html.escape(name)}</text>'
        )
        parts.append(
            f'<text x="{sx:.1f}" y="{by0 + 45:.1f}" text-anchor="middle" fill="#9be7a1" '
            f'font-size="11" font-family="Arial">{stack:,} ({stack_bb}bb)</text>'
        )

        player_cards = hero_cards if is_hero else shown_cards.get(player)
        cy_cards = by0 + box_h + 5
        if player_cards and not is_folded:
            cards_list = player_cards.split()
            cw = 24
            total_w = len(cards_list) * (cw + 3)
            cxs = sx - total_w / 2
            for j, card in enumerate(cards_list):
                parts.append(_card_svg(card, cxs + j * (cw + 3), cy_cards, cw, 32))
        elif not is_folded:
            parts.append(_facedown_svg(sx - 26, cy_cards, 22, 30))
            parts.append(_facedown_svg(sx - 2, cy_cards, 22, 30))

        if acting_player == player and not is_folded:
            parts.append(f'<circle cx="{sx:.1f}" cy="{by0 - 12:.1f}" r="5" fill="#22c55e"/>')

        if pos_label == "BTN":
            dbx, dby = sx + box_w / 2 + 8, sy
            parts.append(f'<circle cx="{dbx:.1f}" cy="{dby:.1f}" r="10" fill="white" '
                        f'stroke="#333" stroke-width="1.5"/>')
            parts.append(f'<text x="{dbx:.1f}" y="{dby + 4:.1f}" text-anchor="middle" '
                        f'font-size="10" font-family="Arial" font-weight="bold">D</text>')

    parts.append("</svg>")
    return "".join(parts)
