"""Exportação do dataset de decisão do Hero (Fase 1 do plano de RL).

Reaproveita a infraestrutura já existente — não reimplementa feature
extraction nem motor de EV/Nash:

- `replay.load`/`replay.list_hands` reconstrói a trajetória da mão.
- `replay_decision.analyze_hero_step` + `.build_decision_analysis_record`
  já fazem toda a reconstrução de facing/pot/stacks e chamam
  `context.analyze_decision` (Nash push/fold isolado OU EV contextual).

Cada linha do dataset é UMA decisão do hero, com três grupos de campo
mantidos deliberadamente separados (ver plano — "outcome != qualidade de
decisão"):

- OUTCOME (resultado observado, nunca usado como label de qualidade):
  `actual_result_bb`, `finish_position`, `eliminated`, `showdown`.
- DECISION QUALITY (vem do motor EV/Nash existente, não do resultado):
  `hero_equity`, `required_equity`, `pot_odds_ratio`, `ev_actual`,
  `ev_best`, `ev_gap`, `reference_action`, `reference_source`.
- BEHAVIOR (o que o hero de fato fez): `action_taken`, `action_class`,
  `bet_size_bb`, `position`, `street`, `effective_stack_bb`,
  `number_of_opponents`, `action_history`.

Quando o motor não consegue calcular uma referência confiável pra uma
decisão específica (ex.: erro de parsing de carta), a linha é mantida
(útil pra Behavioral Cloning depois) mas `reference_source="unavailable"`
e os campos de DECISION QUALITY vêm `None` — nunca inventamos um rótulo.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .. import replay_decision
from ..replay import ReplayHand

# Ações que, do jeito que o motor EV/Nash atual está desenhado, ele sabe
# avaliar ({fold, call, check, push}) — bet/raise sem ir all-in não tem EV
# modelado (o motor não faz sizing de aposta do hero, ver docstring de
# `ev_engine.py`), então mapeiam pra None em vez de inventar um EV.
_ENGINE_ACTIONS = ("fold", "call", "check")


def resolve_actual_engine_action(action: str, all_in: bool) -> str | None:
    """Mapeia a ação real (vocabulário de `actions.action`) pro vocabulário
    de ações que o motor EV/Nash atual avalia. `all_in=True` sempre vira
    "push" (bet/raise/allin podem todos ser o shove final); bet/raise que
    NÃO foi all-in retorna None — não é modelado, não inventamos EV."""
    if all_in:
        return "push"
    if action in _ENGINE_ACTIONS:
        return action
    return None


def normalize_action_class(action: str, all_in: bool) -> str:
    """Taxonomia comportamental (BEHAVIOR) — distinta de
    `resolve_actual_engine_action`: aqui preservamos bet/raise não-all-in
    como categorias próprias (comportamento real do hero), sem colapsar
    tudo em "push" como `decision_stats._acted_push` faz pro caso binário
    Nash (aquilo é uma conveniência de agregação, não uma taxonomia de
    dataset)."""
    return "push" if all_in else action


def hero_decision_steps(rh: ReplayHand) -> list[int]:
    """Índices dos passos do `rh` que são uma decisão do hero analisável
    (mesmo filtro usado por `replay_decision.analyze_hero_step`)."""
    if not rh.hero:
        return []
    return [
        i for i, s in enumerate(rh.steps)
        if s.player == rh.hero and s.action not in replay_decision.NON_DECISION_ACTIONS
    ]


@dataclass
class HandOutcome:
    """OUTCOME da mão inteira — nunca usado como qualidade de decisão."""
    actual_result_bb: float | None
    showdown: bool
    finish_position: int | None
    eliminated: bool


def compute_hand_outcome(conn, rh: ReplayHand) -> HandOutcome:
    """Uma consulta por mão (chamar uma vez, reusar pra todas as decisões
    da mesma mão). `eliminated` é heurística de melhor esforço: stack
    inicial da mão + resultado da mão <= 0 — re-entry/late-reg pode
    distorcer isso (documentado, não escondido)."""
    row = conn.execute(
        """SELECT h.hero_net_chips, t.finish_position
             FROM hands h LEFT JOIN tournaments t
               ON t.site = h.site AND t.tournament_id = h.tournament_id
            WHERE h.site=? AND h.hand_id=?""",
        (rh.site, rh.hand_id),
    ).fetchone()
    net_chips, finish_position = row if row else (None, None)

    actual_result_bb = (net_chips / rh.bb) if (net_chips is not None and rh.bb) else None

    starting_stack = rh.starting_stacks().get(rh.hero) if rh.hero else None
    eliminated = bool(
        starting_stack is not None and net_chips is not None
        and (starting_stack + net_chips) <= 0
    )
    showdown = bool(rh.hero and rh.hero in rh.shown_cards)

    return HandOutcome(
        actual_result_bb=actual_result_bb, showdown=showdown,
        finish_position=finish_position, eliminated=eliminated,
    )


def _action_history(rh: ReplayHand, step_index: int) -> list[dict]:
    """Ações da RUA ATUAL antes do passo do hero — jogador identificado
    por posição ("BTN"/"BB"/...) ou "hero", nunca pelo id bruto do
    jogador (não precisa vazar identidade pra ser útil como feature)."""
    step = rh.steps[step_index]
    start = rh.street_first_index.get(step.street, 0)
    history = []
    for s in rh.steps[start:step_index]:
        history.append({
            "player": "hero" if s.player == rh.hero else (rh.positions.get(s.player) or s.player),
            "action": s.action,
            "amount_bb": (s.amount / rh.bb) if rh.bb else None,
        })
    return history


def build_rl_row(rh: ReplayHand, step_index: int, outcome: HandOutcome,
                  *, equity_iterations: int | None = None) -> dict:
    """Uma linha do dataset pra decisão `step_index` do hero. Nunca
    levanta exceção por conta própria: se o motor de referência falhar
    pra essa decisão específica (carta malformada, etc.), devolve a linha
    mesmo assim com `reference_source="unavailable"` — não descarta dado
    de comportamento só porque a referência de EV não deu.

    `equity_iterations`: repassado pro Monte Carlo do equity engine
    (`equity_engine.DEFAULT_MC_ITERATIONS=20_000` se None). Reduzir isso
    é uma troca CONSCIENTE precisão-por-velocidade pra exports grandes —
    o valor usado fica registrado em `equity_iterations_used` na própria
    linha, nunca escondido. O alvo do Behavioral Cloning é a AÇÃO do
    hero (sempre exata, vem do banco); hero_equity/ev_actual/ev_best/
    ev_gap é que ficam mais ruidosos com menos iterações."""
    step = rh.steps[step_index]
    prev_pot, prev_stacks, _prev_board = rh.state_at(step_index - 1)
    hero_stack = prev_stacks.get(rh.hero)

    base = dict(
        site=rh.site, hand_id=rh.hand_id, tournament_id=rh.tournament_id,
        step_order=step.order, ts=rh.ts,
        street=step.street, position=rh.positions.get(rh.hero),
        hero_cards=rh.hero_cards, board=step.board_so_far or None,
        effective_stack_bb=(hero_stack / rh.bb) if (rh.bb and hero_stack is not None) else None,
        action_taken=step.action,
        action_class=normalize_action_class(step.action, step.all_in),
        bet_size_bb=(step.amount / rh.bb) if rh.bb else None,
        action_history=json.dumps(_action_history(rh, step_index)),
        # OUTCOME — nunca usado como qualidade de decisão, ver docstring do módulo.
        actual_result_bb=outcome.actual_result_bb,
        showdown=outcome.showdown,
        finish_position=outcome.finish_position,
        eliminated=outcome.eliminated,
        equity_iterations_used=equity_iterations,
    )

    try:
        analysis = replay_decision.analyze_hero_step(
            rh, step_index, equity_iterations=equity_iterations,
        )
    except Exception as exc:  # noqa: BLE001 — mão real é imprevisível, não deixamos 1 decisão derrubar o export
        return {
            **base,
            "context_type": None, "model_type": None, "number_of_opponents": None,
            "pot_before_action_bb": None, "bet_faced_bb": None, "call_cost_bb": None,
            "hero_equity": None, "required_equity": None, "pot_odds_ratio": None,
            "reference_action": None, "reference_source": "unavailable",
            "ev_actual": None, "ev_best": None, "ev_gap": None,
            "assumptions": [f"referência indisponível: {exc}"],
        }

    rec = replay_decision.build_decision_analysis_record(
        rh, step_index, analysis, actual_result_bb=outcome.actual_result_bb,
    )

    engine_action = resolve_actual_engine_action(step.action, step.all_in)
    if analysis.nash is not None:
        reference_source = "nash"
        reference_action = analysis.nash.recommendation
        ev_lookup = {"push": analysis.nash.ev_push_bb, "fold": 0.0}
        ev_best = ev_lookup.get(reference_action)
    else:
        c = analysis.contextual
        assert c is not None  # analyze_hero_step sempre retorna nash XOR contextual
        reference_source = "ev_engine"
        best = c.best()
        reference_action = best.action if best else None
        # `DecisionEV.ev` do ev_engine vem em FICHAS CRUAS (os inputs que
        # `context.analyze_decision` passa pra ele — pot_before_bet/hero_stack
        # — são fichas, não BB; só o branch Nash acima já recebe tudo em BB).
        # `build_decision_analysis_record` já faz essa conversão pra
        # ev_call_bb/ev_fold_bb/ev_push_bb — replicamos aqui pros mesmos
        # valores, senão ev_actual/ev_best/ev_gap saem 100-600x maiores que
        # deveriam (bb típico = 100-600 fichas nesses torneios).
        ev_best = (best.ev / rh.bb) if (best and best.ev is not None and rh.bb) else None
        ev_lookup = {
            d.action: (d.ev / rh.bb)
            for d in c.decisions
            if d.applicable and d.ev is not None and rh.bb
        }
    ev_actual = ev_lookup.get(engine_action) if engine_action else None
    ev_gap = (ev_best - ev_actual) if (ev_best is not None and ev_actual is not None) else None

    return {
        **base,
        "context_type": rec["context_type"],
        "model_type": rec["model_type"],
        "number_of_opponents": rec["number_of_opponents"],
        "pot_before_action_bb": rec["pot_before_action_bb"],
        "bet_faced_bb": rec["bet_faced_bb"],
        "call_cost_bb": rec["call_cost_bb"],
        "hero_equity": rec["hero_equity"],
        "required_equity": rec["required_equity"],
        "pot_odds_ratio": rec["pot_odds_ratio"],
        "reference_action": reference_action,
        "reference_source": reference_source,
        "ev_actual": ev_actual,
        "ev_best": ev_best,
        "ev_gap": ev_gap,
        "assumptions": rec["assumptions"],
    }


def process_hand(conn, site: str, hand_id: str,
                  *, equity_iterations: int | None = None) -> tuple[list[dict] | None, str | None]:
    """Processa 1 mão: carrega, computa outcome, monta uma linha por
    decisão do hero. Retorna `(rows, None)` em sucesso, ou `(None, motivo)`
    se a mão foi descartada/deu erro (`motivo == "sem hero/cartas"` é o
    caso "descartada por completo"; qualquer outro texto é erro).

    Única implementação do loop por mão — reusada por `export_dataset`,
    `export_dataset_parallel`, `audit.run_audit` e `audit.run_audit_parallel`
    (a agregação difere em cada um, o processamento por mão não).
    `equity_iterations` ver docstring de `build_rl_row`."""
    from .. import replay

    try:
        rh = replay.load(conn, site, hand_id)
    except Exception as exc:  # noqa: BLE001 — mão real é imprevisível
        return None, f"load falhou: {exc}"
    if rh is None or not rh.hero or not rh.hero_cards:
        return None, "sem hero/cartas"
    try:
        outcome = compute_hand_outcome(conn, rh)
    except Exception as exc:  # noqa: BLE001
        return None, f"outcome falhou: {exc}"

    rows = [
        build_rl_row(rh, i, outcome, equity_iterations=equity_iterations)
        for i in hero_decision_steps(rh)
    ]
    return rows, None


@dataclass
class ExportStats:
    hands_seen: int = 0
    hands_ok: int = 0
    hands_discarded_no_hero: int = 0
    hands_error: int = 0
    decisions: int = 0
    errors: list[str] = field(default_factory=list)


def export_dataset(conn, out_path: str, *, site: str | None = None,
                    format: str = "parquet", equity_iterations: int | None = None,
                    progress=None) -> ExportStats:
    """Percorre todas as mãos (`replay.list_hands`), monta uma linha por
    decisão do hero e grava em `out_path` (parquet por padrão, csv como
    fallback). Uma mão malformada é contada e pulada — nunca derruba o
    export inteiro. Single-thread — pra volumes grandes (milhares de mãos
    com decisão pós-flop, cada uma pagando Monte Carlo do equity engine)
    use `export_dataset_parallel`. `equity_iterations` ver `build_rl_row`."""
    import pandas as pd

    from .. import replay

    stats = ExportStats()
    rows: list[dict] = []
    hands = replay.list_hands(conn, site=site)
    total = len(hands)

    for i, h in enumerate(hands):
        stats.hands_seen += 1
        if progress:
            progress(i, total)
        hand_rows, error = process_hand(
            conn, h["site"], h["hand_id"], equity_iterations=equity_iterations,
        )
        if error == "sem hero/cartas":
            stats.hands_discarded_no_hero += 1
        elif error is not None:
            stats.hands_error += 1
            stats.errors.append(f"{h['site']}/{h['hand_id']}: {error}")
        else:
            rows.extend(hand_rows)
            stats.decisions += len(hand_rows)
            stats.hands_ok += 1

    df = pd.DataFrame(rows)
    if format == "csv":
        df.to_csv(out_path, index=False)
    else:
        df.to_parquet(out_path, index=False)
    return stats


# ---------------- versão paralela (multiprocessing por mão) ----------------
#
# Cada mão é independente (não compartilha estado com nenhuma outra) e o
# custo dominante é o Monte Carlo do equity engine — CPU-bound, puramente
# Python, sem I/O relevante depois de carregada. Isso é "embaraçosamente
# paralelo" por mão: sem GPU envolvida (Monte Carlo aqui é escalar, não
# vetorizado — GPU não ajudaria sem reescrever o motor), mas
# `multiprocessing.Pool` usando os núcleos de CPU já disponíveis dá
# speedup ~linear com o nº de workers. Cada worker abre a PRÓPRIA conexão
# (psycopg2 não é fork-safe compartilhando conexão entre processos).

_WORKER_CONN = None
_WORKER_EQUITY_ITERATIONS = None


def _init_worker(dsn: str, equity_iterations: int | None = None) -> None:
    global _WORKER_CONN, _WORKER_EQUITY_ITERATIONS
    from .. import db as dbm
    _WORKER_CONN = dbm.connect(dsn)
    _WORKER_EQUITY_ITERATIONS = equity_iterations


def _process_hand_ref(hand_ref: tuple[str, str]) -> tuple[str, str, list[dict] | None, str | None]:
    site, hand_id = hand_ref
    rows, error = process_hand(
        _WORKER_CONN, site, hand_id, equity_iterations=_WORKER_EQUITY_ITERATIONS,
    )
    return site, hand_id, rows, error


def _write_df(rows: list[dict], out_path: str, format: str) -> None:
    import pandas as pd

    df = pd.DataFrame(rows)
    tmp_path = f"{out_path}.tmp"
    if format == "csv":
        df.to_csv(tmp_path, index=False)
    else:
        df.to_parquet(tmp_path, index=False)
    os.replace(tmp_path, out_path)  # atômico — nunca deixa out_path pela metade


def export_dataset_parallel(dsn: str, out_path: str, *, site: str | None = None,
                             format: str = "parquet", workers: int | None = None,
                             equity_iterations: int | None = None,
                             checkpoint_every: int = 500,
                             resume: bool = False,
                             progress=None) -> ExportStats:
    """Mesma saída de `export_dataset`, mas processa as mãos em paralelo
    (um processo por worker, cada um com sua própria conexão) — pensado
    pra rodar sobre o volume real (milhares de mãos), não só pros testes.
    `equity_iterations` ver docstring de `build_rl_row` — troca consciente
    de precisão por velocidade, registrada em `equity_iterations_used`.

    Grava `out_path` A CADA `checkpoint_every` mãos processadas (escrita
    atômica via arquivo temporário + rename), não só no final — um job de
    horas rodando em background pode ser interrompido (reinício de sessão,
    reboot da máquina, etc.) e SEM checkpoint isso perde 100% do trabalho
    já feito, não só o que faltava. Com checkpoint, o pior caso é perder só
    o intervalo desde o último checkpoint.

    `resume=True`: se `out_path` já existe, carrega as linhas dele e PULA
    as mãos (site, hand_id) já presentes — só processa o que falta e
    concatena no final. Não reprocessa do zero um export interrompido."""
    import multiprocessing as mp

    import pandas as pd

    from .. import db as dbm
    from .. import replay

    existing_rows: list[dict] = []
    already_done: set[tuple[str, str]] = set()
    if resume and os.path.exists(out_path):
        existing_df = pd.read_parquet(out_path) if format != "csv" else pd.read_csv(out_path)
        existing_rows = existing_df.to_dict("records")
        already_done = set(zip(existing_df["site"], existing_df["hand_id"]))

    setup_conn = dbm.connect(dsn)
    hands = replay.list_hands(setup_conn, site=site)
    setup_conn.close()
    hand_refs = [(h["site"], h["hand_id"]) for h in hands if (h["site"], h["hand_id"]) not in already_done]
    total = len(hand_refs)
    workers = workers or min(os.cpu_count() or 4, 16)

    stats = ExportStats()
    stats.hands_ok = len({hid for _s, hid in already_done})  # retomadas já contam como OK
    rows: list[dict] = list(existing_rows)
    with mp.Pool(processes=workers, initializer=_init_worker,
                 initargs=(dsn, equity_iterations)) as pool:
        for i, (s, hid, hand_rows, error) in enumerate(
            pool.imap_unordered(_process_hand_ref, hand_refs, chunksize=8)
        ):
            stats.hands_seen += 1
            if progress:
                progress(i, total)
            if error == "sem hero/cartas":
                stats.hands_discarded_no_hero += 1
            elif error is not None:
                stats.hands_error += 1
                stats.errors.append(f"{s}/{hid}: {error}")
            else:
                rows.extend(hand_rows)
                stats.decisions += len(hand_rows)
                stats.hands_ok += 1
            if checkpoint_every and stats.hands_seen % checkpoint_every == 0:
                _write_df(rows, out_path, format)
                if progress:
                    progress(i, total)

    _write_df(rows, out_path, format)
    return stats


def temporal_split(df, train: float = 0.7, val: float = 0.15, test: float = 0.15):
    """Split ordenado por `ts` NO NÍVEL DE MÃO (nunca de decisão isolada,
    pra não vazar decisões da mesma mão entre splits). Retorna
    (train_df, val_df, test_df)."""
    assert abs(train + val + test - 1.0) < 1e-9, "train+val+test precisa somar 1.0"

    hands = (
        df[["site", "hand_id", "ts"]]
        .dropna(subset=["ts"])
        .drop_duplicates(subset=["site", "hand_id"])
        .sort_values("ts")
    )
    n = len(hands)
    n_train = int(n * train)
    n_val = int(n * val)

    def _keys(sl):
        return set(zip(sl["site"], sl["hand_id"]))

    train_keys = _keys(hands.iloc[:n_train])
    val_keys = _keys(hands.iloc[n_train:n_train + n_val])
    test_keys = _keys(hands.iloc[n_train + n_val:])

    row_keys = list(zip(df["site"], df["hand_id"]))
    in_train = [k in train_keys for k in row_keys]
    in_val = [k in val_keys for k in row_keys]
    in_test = [k in test_keys for k in row_keys]
    return df[in_train].copy(), df[in_val].copy(), df[in_test].copy()
