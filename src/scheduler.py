"""Execução periódica.

Na POC há duas formas, ambas chamando o mesmo pipeline:

1) Agendador do sistema (recomendado: sobrevive a reinícios)
   Windows:  schtasks /Create /SC MONTHLY /D 1 /ST 03:00 /TN "MPRJ Transparencia" ^
             /TR "C:\\transparencia-inteligente-mprj\\.venv\\Scripts\\python.exe -m src.pipeline run --trigger agendado"
   Linux:    0 3 1 * * cd /opt/transparencia && .venv/bin/python -m src.pipeline run --trigger agendado

2) Processo residente (este módulo):
   python -m src.scheduler --interval-hours 24
   python -m src.scheduler --once

Em produção, o papel deste módulo passa a um orquestrador (Celery beat/Airflow/cron do
Kubernetes) que publica uma tarefa por entidade numa fila; ver docs/DOCUMENTACAO_TECNICA.md §8.
"""
from __future__ import annotations

import argparse
import logging
import random
import time

from src.pipeline import run

log = logging.getLogger("scheduler")


def loop(interval_hours: float, workers: int, once: bool = False) -> None:
    while True:
        started = time.monotonic()
        try:
            run_id = run(workers=workers, trigger="agendado")
            log.info("Execução %s concluída", run_id)
        except Exception:  # o agendador nunca morre por causa de uma execução
            log.exception("Execução falhou; nova tentativa no próximo ciclo")
        if once:
            return
        jitter = random.uniform(0, 0.05) * interval_hours * 3600  # evita picos sincronizados
        pause = max(60.0, interval_hours * 3600 - (time.monotonic() - started) + jitter)
        log.info("Próxima execução em %.1f h", pause / 3600)
        time.sleep(pause)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Agendador simples do pipeline")
    p.add_argument("--interval-hours", type=float, default=24 * 30)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--once", action="store_true")
    a = p.parse_args()
    loop(a.interval_hours, a.workers, a.once)


if __name__ == "__main__":
    main()
