"""Testes do `Hand.position_order()` — nomenclatura de posição por
tamanho de mesa (2 a 9 jogadores). Convenção padrão (conferida com o
usuário): as posições tardias (HJ, CO) aparecem primeiro conforme a mesa
cresce a partir de 4-handed; UTG só aparece a partir de 6-handed. Um bug
anterior fazia o oposto (cortava um array cheio de UTG.../MP... pelo
início), rotulando mesas de 4/5 jogadores como tendo UTG quando essa
posição não existe nelas de verdade — inflava a contagem de mãos "UTG"
em qualquer mesa != 6-handed nos relatórios de Leak Detector/EV por
posição.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.models import Hand, Seat  # noqa: E402

#  position_order() sempre começa no BTN e segue sentido horário (mesma
#  ordem de `occupied[(btn_idx + i) % n]`) — não na ordem "quem age
#  primeiro" que a tabela do usuário usou pra descrever a convenção.
EXPECTED = {
    2: ["SB", "BB"],
    3: ["BTN", "SB", "BB"],
    4: ["BTN", "SB", "BB", "CO"],
    5: ["BTN", "SB", "BB", "HJ", "CO"],
    6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
    7: ["BTN", "SB", "BB", "UTG", "MP", "HJ", "CO"],
    8: ["BTN", "SB", "BB", "UTG", "UTG+1", "MP", "HJ", "CO"],
    9: ["BTN", "SB", "BB", "UTG", "UTG+1", "MP", "MP+1", "HJ", "CO"],
}


def _hand_with_n_seats(n: int, button_seat: int = 1) -> Hand:
    # Seats numerados 1..n — position_order() é relativo ao botão, o
    # número do seat em si não importa pro teste.
    seats = [Seat(seat_no=i, player=f"P{i}", stack=1000) for i in range(1, n + 1)]
    return Hand(
        site="test", hand_id="h", tournament_id="t", timestamp=None, level=None,
        sb=5, bb=10, ante=0, buyin=None, currency=None, table_name=None,
        max_players=n, button_seat=button_seat, seats=seats,
    )


def test_position_order_matches_standard_convention_for_every_table_size():
    for n, expected_labels in EXPECTED.items():
        hand = _hand_with_n_seats(n)
        order = hand.position_order()
        labels = [label for label, _seat in order]
        assert labels == expected_labels, f"n={n}: {labels} != {expected_labels}"


def test_position_order_labels_are_relative_to_button_not_seat_number():
    # Mesmo n=6, botão em seat diferente -> mesma sequência de labels,
    # só começando de um seat_no distinto.
    hand = _hand_with_n_seats(6, button_seat=4)
    order = hand.position_order()
    labels = [label for label, _seat in order]
    assert labels == EXPECTED[6]
    assert order[0][1].seat_no == 4  # BTN é o seat do botão, não seat 1
