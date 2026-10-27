"""Inicia a solução com um único comando: API + painel, já com dados.

    python iniciar.py                 # usa a avaliação real, se houver; senão, a base de demonstração
    python iniciar.py --demo          # força a base de demonstração (portais sintéticos, sem internet)
    python iniciar.py --banco ARQ     # usa um banco SQLite específico
    python iniciar.py --verificar     # só confere o ambiente (Python, dependências, banco) e sai

Funciona igual no CMD, no PowerShell, no Linux e no macOS: não depende de ativar o ambiente
virtual nem de definir variáveis de ambiente no terminal. Ctrl+C encerra API e painel.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REAL_DB = ROOT / "data" / "transparencia.sqlite3"
DEMO_DB = ROOT / "data" / "demo.sqlite3"
REQUIRED = {"fastapi": "fastapi", "uvicorn": "uvicorn", "streamlit": "streamlit", "pandas": "pandas",
            "requests": "requests", "bs4": "beautifulsoup4", "openpyxl": "openpyxl"}


def say(msg: str) -> None:
    print(f"[iniciar] {msg}", flush=True)


def check_python() -> bool:
    """A solução foi testada com Python 3.10 a 3.14."""
    if sys.version_info < (3, 10):
        say(f"Python {sys.version.split()[0]} é antigo demais: instale o Python 3.11 ou mais novo.")
        return False
    say(f"Python {sys.version.split()[0]} ({sys.executable})")
    return True


def check_dependencies() -> bool:
    """Confere se as bibliotecas de requirements.txt estão instaladas neste Python."""
    missing = [pkg for mod, pkg in REQUIRED.items() if importlib.util.find_spec(mod) is None]
    if missing:
        say("Faltam dependências neste Python: " + ", ".join(missing))
        say(f'Instale com:  "{sys.executable}" -m pip install -r requirements.txt')
        return False
    say("Dependências instaladas.")
    return True


def assessments(db: Path) -> int:
    """Número de avaliações gravadas no banco (0 se o arquivo não existe ou está vazio)."""
    if not db.exists():
        return 0
    try:
        with sqlite3.connect(db) as conn:
            return conn.execute("SELECT COUNT(*) FROM assessments").fetchone()[0]
    except sqlite3.Error:
        return 0


def choose_db(args) -> Path | None:
    """Banco a usar: o indicado, a avaliação real (se tiver dados) ou a demonstração (criada se faltar)."""
    if args.banco:
        db = Path(args.banco).resolve()
        if not assessments(db):
            say(f"O banco {db} não existe ou não tem avaliações.")
            return None
        return db
    if not args.demo and assessments(REAL_DB):
        say(f"Usando a avaliação real: {REAL_DB.relative_to(ROOT)} ({assessments(REAL_DB)} avaliações).")
        return REAL_DB
    if not assessments(DEMO_DB):
        say("Criando a base de demonstração (portais sintéticos, sem acesso à internet)...")
        done = subprocess.run([sys.executable, "-m", "src.demo"], cwd=ROOT)
        if done.returncode != 0 or not assessments(DEMO_DB):
            say("Não foi possível criar a base de demonstração (veja a mensagem acima).")
            return None
    say(f"Usando a base de demonstração: {DEMO_DB.relative_to(ROOT)} ({assessments(DEMO_DB)} avaliações).")
    if not args.demo:
        say("Para avaliar os municípios reais (precisa de internet, ~10 min por município): "
            "python -m src.pipeline run")
    return DEMO_DB


def free_port(preferred: int) -> int:
    """A porta preferida, ou a próxima livre (evita conflito com outro serviço na máquina)."""
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"Nenhuma porta livre entre {preferred} e {preferred + 19}")


def wait_http(url: str, proc: subprocess.Popen, seconds: int = 60) -> bool:
    """Espera o serviço responder em `url`; desiste se o processo terminar antes."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as res:
                if res.status == 200:
                    return True
        except OSError:
            time.sleep(0.5)
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Inicia API e painel da solução")
    p.add_argument("--demo", action="store_true", help="usar a base de demonstração")
    p.add_argument("--banco", help="caminho de um banco SQLite com avaliações")
    p.add_argument("--verificar", action="store_true", help="só conferir o ambiente e sair")
    p.add_argument("--sem-navegador", action="store_true", help="não abrir o navegador")
    args = p.parse_args()
    os.chdir(ROOT)

    if not (check_python() and check_dependencies()):
        return 1
    db = choose_db(args)
    if db is None:
        return 1
    if args.verificar:
        say("Ambiente pronto. Para iniciar: python iniciar.py")
        return 0

    api_port, ui_port = free_port(8000), free_port(8501)
    api_url, ui_url = f"http://127.0.0.1:{api_port}", f"http://localhost:{ui_port}"
    env = {**os.environ, "MPRJ_DB_PATH": str(db), "MPRJ_API_URL": api_url, "PYTHONPATH": str(ROOT)}
    procs: list[subprocess.Popen] = []
    try:
        say(f"Iniciando a API em {api_url} ...")
        api = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1",
                                "--port", str(api_port), "--log-level", "warning"], cwd=ROOT, env=env)
        procs.append(api)
        if not wait_http(f"{api_url}/health", api):
            say("A API não respondeu. Veja a mensagem de erro acima.")
            return 1
        say(f"Iniciando o painel em {ui_url} ...")
        ui = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app/dashboard.py",
                               "--server.port", str(ui_port), "--server.headless", "true",
                               "--browser.gatherUsageStats", "false"], cwd=ROOT, env=env)
        procs.append(ui)
        if not wait_http(f"{ui_url}/_stcore/health", ui):
            say("O painel não respondeu. Veja a mensagem de erro acima.")
            return 1
        print()
        say(f"Painel:          {ui_url}")
        say(f"API (Swagger):   {api_url}/docs")
        say("Ctrl+C para encerrar.")
        if not args.sem_navegador:
            webbrowser.open(ui_url)
        while all(proc.poll() is None for proc in procs):
            time.sleep(1)
        say("Um dos serviços terminou inesperadamente (veja a mensagem acima).")
        return 1
    except KeyboardInterrupt:
        say("Encerrando...")
        return 0
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
