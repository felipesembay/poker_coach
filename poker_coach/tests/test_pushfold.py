"""Testes do motor de Push/Fold.

Os testes do solver de Nash usam uma matriz/ranking SINTÉTICOS pequenos
(não a matriz real de 169 classes, que leva minutos pra construir) —
verificam a mecânica do ponto fixo, não os números reais de push/fold.
A matriz real fica cacheada em disco (pushfold/matrix_cache.json) e só
precisa ser construída uma vez, fora do test suite.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from poker_coach import db as dbm
from poker_coach.parsers import partypoker
from poker_coach.pushfold import analyze as pf
from poker_coach.pushfold import equity as eq
from poker_coach.pushfold import nash

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEST_DSN = "postgresql://postgres:airflow@172.17.0.3:5432/poker_coach_test"


def test_hand_evaluator_category_ordering():
    def cards(s):
        return eq.parse_hand(s)

    royal = cards("Ah Kh") + cards("Qh Jh Th 2c 3d")
    quads = cards("9s 9h") + cards("9c 9d Ks 2c 3d")
    full_house = cards("9h 9d") + cards("9c 2h 2d Ks 3d")
    flush = cards("Ah 2h") + cards("5h 9h Kh 2c 3d")
    straight = cards("5h 6d") + cards("7c 8s 9h 2c 3d")
    trips = cards("9h 9d") + cards("9c 2h 5d Ks 3d")
    two_pair = cards("9h 9d") + cards("2h 2d 5c Ks 3d")
    assert eq.best_of_7(royal) > eq.best_of_7(quads) > eq.best_of_7(full_house)
    assert eq.best_of_7(full_house) > eq.best_of_7(flush) > eq.best_of_7(straight)
    assert eq.best_of_7(straight) > eq.best_of_7(trips) > eq.best_of_7(two_pair)


def test_wheel_straight():
    wheel = eq.parse_hand("Ah 2d") + eq.parse_hand("3c 4s 5h 9c Kd")
    cat, top = eq.hand_rank5(wheel[:5])
    assert (cat, top) == (4, 5)  # categoria "straight", topo = 5 (a roda é a straight mais baixa)


def test_hand_classes_and_combos():
    classes = eq.all_hand_classes()
    assert len(classes) == 169
    assert sum(eq.class_combo_count(c) for c in classes) == 1326
    assert eq.class_of(eq.parse_hand("Ah Kh")) == "AKs"
    assert eq.class_of(eq.parse_hand("Ah Kd")) == "AKo"
    assert eq.class_of(eq.parse_hand("9h 9d")) == "99"


def test_range_top_pct_is_monotonic_in_size():
    ranking = ["AA", "KK", "QQ", "JJ", "AKs", "AKo", "72o"]
    small = eq.range_top_pct(5, ranking)
    big = eq.range_top_pct(50, ranking)
    assert set(small) <= set(big)
    assert "AA" in small  # a melhor mão sempre entra em qualquer range positiva


def _synthetic_ranking_and_matrix():
    """8 classes com força estritamente decrescente e equity coerente
    entre elas (classe i vence classe j com prob. proporcional à
    distância no ranking) — o suficiente pra testar a mecânica do
    ponto fixo sem gastar minutos calculando a matriz real."""
    # nomes de 2 letras (não classes reais) só pra combinar com o formato
    # que class_combo_count() espera (len==2 => trata como "par", peso 6
    # uniforme) sem precisar de um combo_count injetável no solver.
    ranking = ["ZZ", "YY", "XX", "WW", "VV", "UU", "TT", "SS"]
    strength = {c: (len(ranking) - i) / len(ranking) for i, c in enumerate(ranking)}
    matrix = {}
    for a in ranking:
        for b in ranking:
            if a == b:
                matrix[f"{a}|{b}"] = 0.5
            else:
                sa, sb = strength[a], strength[b]
                matrix[f"{a}|{b}"] = sa / (sa + sb)
    return ranking, matrix


def test_nash_solve_shove_range_is_monotonic():
    """Numa matriz sintética onde força de mão é totalmente ordenada, o
    equilíbrio deve empurrar as mãos mais fortes e nunca uma mais fraca
    sem empurrar uma mais forte (monotonicidade básica do problema)."""
    ranking, matrix = _synthetic_ranking_and_matrix()
    # stack curto, pot pequeno: deveria empurrar quase tudo
    wide = nash.solve(effective_bb=6, pot_bb=1.5, ranking=ranking, matrix=matrix, iterations=15)
    assert wide.shove_classes[0] == "ZZ"
    idx = [ranking.index(c) for c in wide.shove_classes]
    assert idx == sorted(idx)  # nenhum "buraco" no meio da range por força

    # stack fundo: deveria empurrar bem menos mãos
    deep = nash.solve(effective_bb=40, pot_bb=1.5, ranking=ranking, matrix=matrix, iterations=15)
    assert len(deep.shove_classes) <= len(wide.shove_classes)


def test_analyze_scope_skips_limped_pot():
    """A mão 1 do fixture do PartyPoker tem 3 calls antes do herói
    (Player2/3/4 dão call) — não é mais um spot de "abertura" (unopened),
    então o analisador deve pular, não tentar aplicar o modelo HU vs BB
    fora do escopo dele."""
    hands = partypoker.parse_file((ROOT / "samples/partypoker_sample.txt").read_text())
    conn = dbm.connect(TEST_DSN)
    for t in ["actions", "seats", "showdowns", "results", "hands", "tournaments"]:
        conn.execute(f"DELETE FROM {t}")
    for h in hands:
        dbm.insert_hand(conn, h)
    conn.commit()

    h1 = hands[0]
    row = pf.analyze_hand_row(conn, h1.site, h1.hand_id)
    assert row is None  # pote já tinha 3 calls antes do herói: fora do escopo


if __name__ == "__main__":
    test_hand_evaluator_category_ordering()
    test_wheel_straight()
    test_hand_classes_and_combos()
    test_range_top_pct_is_monotonic_in_size()
    test_nash_solve_shove_range_is_monotonic()
    test_analyze_scope_skips_limped_pot()
    print("OK: todos os testes de pushfold passaram")
