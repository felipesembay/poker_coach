"""Testes do motor de ICM (Malmuth-Harville)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import icm


def test_conservation():
    """A soma das equities de todo mundo tem que bater com a soma dos prêmios."""
    eqs = icm.icm_equity([500, 300, 200], [50, 30, 20])
    assert abs(sum(eqs) - 100) < 1e-9


def test_heads_up_closed_form():
    """Heads-up é um caso fechado: equity(A) = P(A ganha)*prêmio1 + P(B ganha)*prêmio2."""
    stacks = [700, 300]
    payouts = [60, 40]
    eqs = icm.icm_equity(stacks, payouts)
    p_a = 700 / 1000
    expected_a = p_a * 60 + (1 - p_a) * 40
    assert abs(eqs[0] - expected_a) < 1e-9


def test_symmetric_stacks_give_symmetric_equity():
    eqs = icm.icm_equity([100, 100, 100, 100], [40, 30, 20, 10])
    assert all(abs(e - 25.0) < 1e-9 for e in eqs)


def test_classic_icm_discount_effect():
    """Efeito clássico de ICM: com mais de um prêmio pago, o stack GRANDE
    vale MENOS por ficha em $ do que sua fatia de fichas sugere (porque o
    stack pequeno já tem o 2º lugar quase garantido)."""
    stacks = [900, 100]
    payouts = [80, 20]
    eqs = icm.icm_equity(stacks, payouts)
    chip_share_big = stacks[0] / sum(stacks)
    icm_share_big = eqs[0] / sum(payouts)
    assert icm_share_big < chip_share_big


def test_risk_premium_sign():
    """Risk premium positivo pro stack grande (ICM desconta ele), negativo
    pro stack curto (ICM favorece ele relativo à fatia de fichas)."""
    stacks = [900, 100]
    payouts = [80, 20]
    rp_big = icm.risk_premium_pct(stacks, payouts, 0)
    rp_short = icm.risk_premium_pct(stacks, payouts, 1)
    assert rp_big > 0
    assert rp_short < 0


def test_push_fold_icm_ev_certain_win_beats_fold():
    stacks = [1000, 5000, 5000]
    payouts = [60, 30, 10]
    fold_ev, push_ev = icm.push_fold_icm_ev(
        stacks, payouts, hero_idx=0, villain_idx=1,
        effective_stack=1000, pot_dead=150, equity_vs_call=1.0, p_call=1.0)
    assert push_ev > fold_ev


def test_push_fold_icm_ev_certain_loss_equals_min_cash():
    """Se o herói perde o confronto com certeza (equity=0) e é sempre
    pago, o resultado é a eliminação: ele fica só com o valor garantido
    do último lugar restante (aqui, o 3º prêmio)."""
    stacks = [1000, 5000, 5000]
    payouts = [60, 30, 10]
    _fold_ev, push_ev = icm.push_fold_icm_ev(
        stacks, payouts, hero_idx=0, villain_idx=1,
        effective_stack=1000, pot_dead=150, equity_vs_call=0.0, p_call=1.0)
    assert abs(push_ev - 10) < 1e-9


def test_push_fold_icm_ev_uncalled_beats_fold_slightly():
    """Se o vilão nunca paga, empurrar só ganha o dead money de graça —
    deve ser um pouco melhor que fold, nunca pior."""
    stacks = [1000, 5000, 5000]
    payouts = [60, 30, 10]
    fold_ev, push_ev = icm.push_fold_icm_ev(
        stacks, payouts, hero_idx=0, villain_idx=1,
        effective_stack=1000, pot_dead=150, equity_vs_call=0.5, p_call=0.0)
    assert push_ev > fold_ev


if __name__ == "__main__":
    test_conservation()
    test_heads_up_closed_form()
    test_symmetric_stacks_give_symmetric_equity()
    test_classic_icm_discount_effect()
    test_risk_premium_sign()
    test_push_fold_icm_ev_certain_win_beats_fold()
    test_push_fold_icm_ev_certain_loss_equals_min_cash()
    test_push_fold_icm_ev_uncalled_beats_fold_slightly()
    print("OK: todos os testes de ICM passaram")
