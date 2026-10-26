"""The in-app Help guide must exist, carry its flow charts, and mention every
top-level tab, so it can't silently drift behind the app."""

from __future__ import annotations

import re
from pathlib import Path

from etools.ui.tabs.help_tab import GUIDE_PATH, load_guide

APP = Path(__file__).resolve().parents[1] / "etools" / "ui" / "app.py"


def test_guide_ships_inside_the_package() -> None:
    # The portable bundle copies only etools/, so the guide must live there.
    assert GUIDE_PATH.is_file()
    assert "etools" in GUIDE_PATH.parts


def test_guide_has_flow_charts() -> None:
    assert load_guide().count("```mermaid") >= 5


def test_guide_mentions_every_tab() -> None:
    tabs = re.findall(r'ui\.tab\("([^"]+)"', APP.read_text(encoding="utf-8"))
    assert tabs, "no tabs found in app.py"
    guide = load_guide()
    missing = [t for t in tabs if t not in guide]
    assert not missing, f"Help guide doesn't mention tab(s): {missing}"
