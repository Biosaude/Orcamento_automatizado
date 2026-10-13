from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGES = (
    "Dashboard",
    "Solicitações",
    "Simulador",
    "Produtos",
    "Estoque",
    "Hospitais",
    "Histórico",
    "Configurações",
)
APP = Path(__file__).resolve().parents[1] / "frontend" / "app.py"


@pytest.mark.parametrize("page", PAGES)
def test_all_pages_render_without_operational_controls(page):
    app = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not app.exception
    assert tuple(app.sidebar.radio[0].options) == PAGES
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception
    assert app.header[0].value == page
    assert app.info
    assert not app.button
    assert not app.metric
