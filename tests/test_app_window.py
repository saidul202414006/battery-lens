import pytest
import os
import customtkinter as ctk
from unittest.mock import MagicMock
from core.database import Database
from ui.app_window import AppWindow


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_app_window.db")
    db = Database(db_path)
    yield db
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass


def test_app_window_creation(test_db):
    # E1: AppWindow is now CTkToplevel — requires a master (Tk root)
    root = ctk.CTk()
    root.withdraw()

    on_close = MagicMock()
    app = AppWindow(root, test_db, on_close)

    assert app.title() == "Battery Lens"

    # Test tabs
    tabs = app.tabs
    assert "Dashboard" in tabs
    assert "History" in tabs

    # Test window hide logic
    app._on_close()
    assert app.state() == "withdrawn"
    on_close.assert_called_once()

    # Test show window
    app.show_window("History")
    assert app.state() == "normal"
    assert app.tabview.get() == "History"

    app.destroy()
    root.destroy()
