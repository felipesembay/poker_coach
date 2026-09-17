import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.pot_odds import PotOddsInputError, calculate_pot_odds


def test_simple_facing_bet_matches_spec_example():
    result = calculate_pot_odds(pot_before_bet=10.0, bet_size=5.0)
    assert result.pot_before_bet == 10.0
    assert result.villain_bet == 5.0
    assert result.hero_call_cost == 5.0
    assert result.pot_after_call == 20.0
    assert result.required_equity == pytest.approx(0.25)
    assert result.pot_odds_ratio == "3:1"
    assert result.is_partial_call is False
    assert result.hero_stack_after_call is None


def test_facing_raise_does_not_double_count_heros_prior_investment():
    # Hero deu bet de 3, vilão resubiu pra 9 total. Hero só precisa
    # completar 6 (9 - 3), não pagar os 9 inteiros de novo.
    result = calculate_pot_odds(
        pot_before_bet=10.0, bet_size=9.0, hero_already_in=3.0, facing="raise"
    )
    assert result.hero_call_cost == 6.0
    assert result.pot_after_call == pytest.approx(10.0 + 9.0 + 6.0)
    assert result.facing == "raise"


def test_facing_allin_with_partial_call_when_stack_insufficient():
    result = calculate_pot_odds(
        pot_before_bet=20.0, bet_size=50.0, hero_stack=30.0, facing="allin"
    )
    assert result.is_partial_call is True
    assert result.hero_call_cost == 30.0  # limitado pelo stack, não pelos 50 cheios
    assert result.pot_after_call == pytest.approx(20.0 + 50.0 + 30.0)
    assert result.hero_stack_after_call == 0.0
    assert any("parcial" in a for a in result.assumptions)


def test_full_call_when_stack_covers_the_bet():
    result = calculate_pot_odds(pot_before_bet=20.0, bet_size=10.0, hero_stack=100.0)
    assert result.is_partial_call is False
    assert result.hero_call_cost == 10.0
    assert result.hero_stack_after_call == 90.0


def test_multiway_includes_other_players_money_already_in():
    # Vilão apostou 10, outro jogador já pagou 10 antes do hero decidir.
    result = calculate_pot_odds(
        pot_before_bet=15.0, bet_size=10.0, additional_money_in=10.0
    )
    assert result.pot_after_call == pytest.approx(15.0 + 10.0 + 10.0 + 10.0)
    assert result.required_equity == pytest.approx(10.0 / (15.0 + 10.0 + 10.0 + 10.0))
    assert any("Multiway" in a for a in result.assumptions)


def test_pot_odds_ratio_rounds_cleanly():
    result = calculate_pot_odds(pot_before_bet=0.0, bet_size=10.0)  # pote 10, custo 10 -> 1:1
    assert result.pot_odds_ratio == "1:1"


def test_rejects_negative_pot_before_bet():
    with pytest.raises(PotOddsInputError, match="pot_before_bet"):
        calculate_pot_odds(pot_before_bet=-1.0, bet_size=5.0)


def test_rejects_non_positive_bet_size():
    with pytest.raises(PotOddsInputError, match="bet_size"):
        calculate_pot_odds(pot_before_bet=10.0, bet_size=0.0)


def test_rejects_hero_already_in_greater_than_bet_size():
    with pytest.raises(PotOddsInputError, match="hero_already_in"):
        calculate_pot_odds(pot_before_bet=10.0, bet_size=5.0, hero_already_in=6.0)


def test_rejects_when_hero_already_matched_the_bet():
    with pytest.raises(PotOddsInputError, match="já igualou"):
        calculate_pot_odds(pot_before_bet=10.0, bet_size=5.0, hero_already_in=5.0)


def test_rejects_zero_or_negative_hero_stack():
    with pytest.raises(PotOddsInputError, match="hero_stack"):
        calculate_pot_odds(pot_before_bet=10.0, bet_size=5.0, hero_stack=0.0)


def test_rejects_invalid_facing():
    with pytest.raises(PotOddsInputError, match="facing"):
        calculate_pot_odds(pot_before_bet=10.0, bet_size=5.0, facing="raise-limped")
