"""Pipeline de dados pro Personal Poker Coach (Fase 0/1 do plano de RL).

Escopo atual: auditoria (`audit.py`) e exportação de dataset de decisão
(`export.py`) + backfill de `decision_analysis` (`backfill_decision_analysis.py`).
Não contém nenhum modelo de RL/ML ainda — só a extração de features/labels
a partir das mãos já importadas, reaproveitando `replay_decision.py` e
`context.py` (não reimplementa equity/EV/Nash).

Princípio que rege todo este pacote: OUTCOME (resultado real da mão,
`actual_result_bb`/`finish_position`/`eliminated`/`showdown`) nunca é usado
como substituto de DECISION QUALITY (`ev_actual`/`ev_best`/`ev_gap`,
derivados do motor EV/Nash existente). Ver `export.py` para a separação
exata dos campos.
"""
