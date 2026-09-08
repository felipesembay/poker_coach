#!/usr/bin/env python3
"""Teste local de comportamento diante de limites de consulta.

Este arquivo nao chama servicos de terceiros. Ele sobe um servidor HTTP local e
exercita um cliente que bloqueia novas chamadas apos o limite diario definido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable


DAILY_LIMIT = 5


@dataclass
class DailyLimit:
    limit: int = DAILY_LIMIT
    day: date = field(default_factory=date.today)
    used: int = 0

    def consume(self) -> None:
        if date.today() != self.day:
            self.day, self.used = date.today(), 0
        if self.used >= self.limit:
            raise RuntimeError(f"Limite local de {self.limit} consultas/dia atingido.")
        self.used += 1


def fetch(request: Callable[[], tuple[int, dict]], limit: DailyLimit) -> dict:
    """Consome a cota antes da chamada e trata respostas de limitação."""
    limit.consume()
    status, payload = request()
    if status in (401, 403, 429):
        raise RuntimeError(f"Servidor recusou a consulta (HTTP {status}); interrompendo.")
    if not 200 <= status < 300:
        raise RuntimeError(f"Falha inesperada do servidor (HTTP {status}).")
    return payload


def main() -> None:
    limit = DailyLimit()
    calls = 0

    def mock_request() -> tuple[int, dict]:
        nonlocal calls
        calls += 1
        if calls == 10:
            return 429, {"error": "rate_limited"}
        return 200, {"ok": True, "call": calls}

    for attempt in range(1, 8):
        try:
            print(f"Tentativa {attempt}: {fetch(mock_request, limit)}")
        except RuntimeError as error:
            print(f"Tentativa {attempt}: {error}")
            if "Servidor recusou" in str(error) or "Limite local" in str(error):
                break


if __name__ == "__main__":
    main()
