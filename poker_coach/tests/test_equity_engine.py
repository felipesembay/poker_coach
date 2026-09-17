import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach.equity_engine import (
    EquityInputError,
    EquityOpponent,
    calculate_equity,
)


def test_river_exact_hero_wins_higher_pair():
    result = calculate_equity(
        street="river",
        hero_cards=["Qs", "Qh"],
        board=["2c", "7d", "Jh", "4s", "6c"],
        opponents=[EquityOpponent(player_id="v1", cards=["9d", "9c"])],
    )
    assert result.simulation_method == "exact"
    assert result.iterations == 1
    assert result.win_probability == 1.0
    assert result.tie_probability == 0.0
    assert result.loss_probability == 0.0
    assert result.hero_equity == 1.0
    assert result.confidence_interval is None
    assert result.outs == []  # river: não há mais outs


def test_river_exact_board_plays_ties():
    result = calculate_equity(
        street="river",
        hero_cards=["2s", "3d"],
        board=["Ah", "Kh", "Qh", "Jh", "Th"],  # royal flush no board
        opponents=[EquityOpponent(player_id="v1", cards=["4c", "5s"])],
    )
    assert result.simulation_method == "exact"
    assert result.tie_probability == 1.0
    assert result.hero_equity == 0.5


def test_hand_vs_range_is_exact_for_small_range_and_matches_known_poker_math():
    # AA vs QQ-only range, board sem overcard/flush/straight pra QQ — AA
    # deve ficar bem à frente (fato conhecido: AA vs QQ ~80% preflop; aqui
    # é pós-flop com board neutro, deve ficar na mesma faixa).
    result = calculate_equity(
        street="flop",
        hero_cards=["Ah", "Ad"],
        board=["2c", "7d", "9h"],
        opponents=[EquityOpponent(player_id="v1", range_classes=["QQ"])],
    )
    assert result.simulation_method == "exact"
    assert 0.85 < result.hero_equity < 0.95
    total = result.win_probability + result.tie_probability + result.loss_probability
    assert total == pytest.approx(1.0)


def test_multiway_uses_monte_carlo_and_returns_valid_probabilities():
    result = calculate_equity(
        street="flop",
        hero_cards=["Ah", "Ad"],
        board=["2c", "7d", "9h"],
        opponents=[
            EquityOpponent(player_id="v1"),
            EquityOpponent(player_id="v2"),
        ],
        iterations=2000,
        seed=42,
    )
    assert result.simulation_method == "monte_carlo"
    assert result.num_opponents == 2
    assert result.confidence_interval is not None
    lo, hi = result.confidence_interval
    assert 0.0 <= lo <= result.hero_equity <= hi <= 1.0
    total = result.win_probability + result.tie_probability + result.loss_probability
    assert total == pytest.approx(1.0)
    # outs não fazem sentido em multiway — motor não inventa esse dado
    assert result.outs == []
    assert result.turn_improvement_probability is None
    assert result.river_improvement_probability is None


def test_outs_flush_draw_excludes_cards_that_pair_villain_into_a_boat_or_quads():
    # Hero tem 4 espadas (flush draw) no turn; vilão já tem trinca de reis.
    # Toda espada restante completa o flush do hero e vence a trinca — MENOS
    # o Ks (dá quadra de reis) e o Js (empareia o Jc do board, dando reis
    # cheios de valetes pro vilão) — ambos batem o flush do hero.
    result = calculate_equity(
        street="turn",
        hero_cards=["2s", "5s"],
        board=["9s", "4s", "Jc", "Kd"],
        opponents=[EquityOpponent(player_id="v1", cards=["Kh", "Kc"])],
    )
    expected_outs = {"3s", "6s", "7s", "8s", "Ts", "Qs", "As"}
    assert set(result.outs) == expected_outs
    assert "Ks" not in result.outs
    assert "Js" not in result.outs
    remaining = 52 - 2 - 4 - 2  # hero + board + villain
    assert result.river_improvement_probability == pytest.approx(len(expected_outs) / remaining)
    assert result.turn_improvement_probability is None  # já estamos no turn


def test_already_ahead_hero_has_no_outs():
    # AA vs KK num board seco — hero já está à frente, "outs" fica vazio
    # (conceito é sobre virar o jogo, não sobre continuar ganhando).
    result = calculate_equity(
        street="flop",
        hero_cards=["Ah", "Ad"],
        board=["2c", "7d", "9h"],
        opponents=[EquityOpponent(player_id="v1", cards=["Ks", "Kd"])],
    )
    assert result.outs == []


def test_rejects_duplicate_card():
    with pytest.raises(EquityInputError, match="duplicada"):
        calculate_equity(
            street="river",
            hero_cards=["As", "As"],
            board=["2c", "7d", "Jh", "4s", "6c"],
            opponents=[EquityOpponent(player_id="v1", cards=["9d", "9c"])],
        )


def test_rejects_wrong_board_size_for_street():
    with pytest.raises(EquityInputError, match="board incompleto"):
        calculate_equity(
            street="flop",
            hero_cards=["As", "Ks"],
            board=["2c", "7d"],  # flop precisa de 3
            opponents=[EquityOpponent(player_id="v1", cards=["9d", "9c"])],
        )


def test_rejects_invalid_range_class():
    with pytest.raises(EquityInputError, match="classes de mão inválidas"):
        calculate_equity(
            street="flop",
            hero_cards=["As", "Ks"],
            board=["2c", "7d", "9h"],
            opponents=[EquityOpponent(player_id="v1", range_classes=["ZZ"])],
        )


def test_rejects_invalid_street():
    with pytest.raises(EquityInputError, match="street inválida"):
        calculate_equity(
            street="bogus",
            hero_cards=["As", "Ks"],
            board=[],
            opponents=[EquityOpponent(player_id="v1", cards=["9d", "9c"])],
        )


def test_rejects_cards_and_range_together():
    with pytest.raises(EquityInputError, match="cards.*OU.*range_classes"):
        calculate_equity(
            street="flop",
            hero_cards=["As", "Ks"],
            board=["2c", "7d", "9h"],
            opponents=[
                EquityOpponent(player_id="v1", cards=["9d", "9c"], range_classes=["QQ"])
            ],
        )
