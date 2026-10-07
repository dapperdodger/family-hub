import importlib.util
import json
from pathlib import Path

FIX = Path(__file__).parent / "js" / "fixtures"


def test_the_season_calendar_fixture_is_current():
    spec = importlib.util.spec_from_file_location("make_season_calendar", FIX / "make_season_calendar.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert json.loads((FIX / "season-calendar.json").read_text(encoding="utf-8")) == mod.rows()
