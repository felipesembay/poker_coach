"""Testes básicos dos parsers e das métricas derivadas.

samples/partypoker_sample.txt contém 2 mãos reais extraídas de um
export do PartyPoker ("My Game" -> Export Hands), formato atual da
sala (cabeçalho "Tourney ... (MTT Tournament #N)", blinds/antes/calls
entre parênteses, resultado via "** Summary **" com "net +/-N").
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.parsers import partypoker, pokerstars

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_partypoker():
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())
    assert len(hands) == 2
    h1, h2 = hands
    assert h1.tournament_id == "420849778" and h1.hand_id == "17801119293899665mun14ke"
    assert h1.hero == "Hero" and h1.hero_cards == "Kh 2h"
    assert h1.hero_position() == "UTG" and h1.hero_stack_bb() == 14.99
    assert h1.hero_vpip() is True and h1.hero_pfr() is True
    # Hero perde a mão inteira all-in (side pot) -> net = -stack investido
    assert h1.hero_net_chips() == -899196
    assert h1.board == "5c Td 9d 7d 7h"
    # conservação de fichas: soma dos resultados de todos os jogadores == 0
    assert sum(h1.results.values()) == 0
    # showdown: cartas reveladas vêm do "** Summary **" (não tem linha
    # "shows" nessa sala), casadas com o colchete logo após net/lost
    assert h1.shown_cards == {"Player3": "8h 6c", "Player4": "4c Tc", "Hero": "Kh 2h"}

    assert h2.hero_position() == "UTG"
    assert h2.hero_vpip() is False
    assert h2.hero_net_chips() == -7500  # fold, perde só o ante postado
    assert sum(h2.results.values()) == 0


def test_partypoker_all_in_raise_marks_flag():
    """'Nome is all-In.' (sem valor) deve marcar a ação anterior do
    jogador como all_in, não criar uma ação fantasma nem duplicar
    fichas contadas."""
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())
    h1 = hands[0]
    hero_actions = [a for a in h1.actions if a.player == "Hero" and a.street == "preflop"]
    raise_action = next(a for a in hero_actions if a.action == "raise")
    assert raise_action.all_in is True
    assert raise_action.amount == 831696  # incremento, não o total "to 891696"


def test_pokerstars():
    path = ROOT / "samples/pokerstars_sample.txt"
    if not path.exists():
        try:
            import pytest
            pytest.skip(
                "samples/pokerstars_sample.txt ausente — adicione uma hand "
                "history real do PokerStars em samples/pokerstars/ para "
                "validar o parser (hoje ele nunca foi testado contra um "
                "export real)."
            )
        except ImportError:
            print("PULADO: samples/pokerstars_sample.txt ausente — parser "
                  "do PokerStars nunca foi testado contra um export real.")
            return
    hands = pokerstars.parse_file(path.read_text())
    assert len(hands) == 1
    h = hands[0]
    assert h.tournament_id == "3448228870" and h.buyin == 11.0
    assert h.hero == "hero_br" and h.level == 5
    assert h.hero_pfr() is True
    assert h.hero_net_chips() == 435


if __name__ == "__main__":
    test_partypoker()
    test_partypoker_all_in_raise_marks_flag()
    test_pokerstars()
    print("OK: todos os testes passaram (ou pulados, ver acima)")
