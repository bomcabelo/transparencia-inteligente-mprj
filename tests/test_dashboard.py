"""O painel abre e renderiza as três abas sem erro, independentemente de como é iniciado.

Regressão de 27/10/2026: com `streamlit run app/dashboard.py` (sem `python -m`), a raiz do projeto
não ficava no sys.path e a aba "Por entidade" falhava com `ModuleNotFoundError: No module named 'app'`,
impedindo também a aba "Checklist" de aparecer. O AppTest reproduz esse cenário: executa o script
como o Streamlit faz, sem a raiz do projeto garantida no caminho de importação.
"""
import sys
from datetime import date
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

import pytest

pytest.importorskip("streamlit")
from fastapi.testclient import TestClient  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from api.main import app  # noqa: E402

DASHBOARD = str(Path(__file__).resolve().parents[1] / "app" / "dashboard.py")


class _Resp:
    def __init__(self, r):
        self._r, self.status_code = r, r.status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._r.json()


def test_dashboard_renders_all_tabs_without_errors(tmp_db, monkeypatch):
    from src.demo import seed
    seed(tmp_db, today=date(2026, 10, 13))
    client = TestClient(app)

    def fake_get(url, params=None, timeout=None):  # o painel fala com a API só por HTTP
        return _Resp(client.get(urlsplit(url).path, params=params))

    root = str(Path(DASHBOARD).parents[1])
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in ("", ".", root)])
    for name in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        monkeypatch.delitem(sys.modules, name)
    with mock.patch("requests.get", fake_get):
        at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert len(at.tabs) == 3 and len(at.metric) >= 3
