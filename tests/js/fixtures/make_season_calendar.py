"""Regenerates season-calendar.json: which season must paint on the edge days of every window.

An independent oracle: it re-derives Easter (the Gregorian computus) and the nth-weekday holidays in Python and
applies the registry ORDER from the spec, so the JS test cannot just mirror theme.js.
Run:  python tests/js/fixtures/make_season_calendar.py
tests/test_season_calendar_fixture.py fails if the committed JSON is stale.
"""
import datetime as dt
import json
from pathlib import Path

D = dt.timedelta
YEARS = (2008, 2026, 2027, 2028, 2030, 2038)   # 2008/2038 are the earliest/latest Easters; 2028 is a leap year; 2030's Thanksgiving touches Dec 1
ORDER = ["newyears", "christmas", "mlkday", "valentines", "winter", "stpatricks", "easter", "mothersday", "spring",
         "fathersday", "julyfourth", "summer", "halloween", "thanksgiving", "fall"]


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e, f = b // 4, b % 4, (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    return dt.date(y, month, ((h + l - 7 * m + 114) % 31) + 1)


def nth(y, month, weekday_sunday0, n):
    first = dt.date(y, month, 1)
    return first + D(days=(weekday_sunday0 - (first.weekday() + 1) % 7) % 7 + 7 * (n - 1))


def window(sid, y):
    mom, dad, mlk, thx = nth(y, 5, 0, 2), nth(y, 6, 0, 3), nth(y, 1, 1, 3), nth(y, 11, 4, 4)
    return {
        "christmas": (dt.date(y, 12, 1), dt.date(y, 12, 26)),
        "valentines": (dt.date(y, 2, 1), dt.date(y, 2, 14)),
        "stpatricks": (dt.date(y, 3, 1), dt.date(y, 3, 17)),
        "julyfourth": (dt.date(y, 6, 25), dt.date(y, 7, 4)),
        "spring": (dt.date(y, 3, 1), dt.date(y, 5, 31)),
        "summer": (dt.date(y, 6, 1), dt.date(y, 8, 31)),
        "halloween": (dt.date(y, 10, 1), dt.date(y, 10, 31)),
        "fall": (dt.date(y, 9, 1), dt.date(y, 11, 30)),
        "easter": (easter(y) - D(14), easter(y) + D(1)),
        "mothersday": (mom - D(6), mom),
        "fathersday": (dad - D(3), dad),
        "mlkday": (mlk - D(3), mlk),
        "thanksgiving": (thx - D(10), thx + D(3)),
    }[sid]


def holds(sid, d):
    if sid == "newyears":
        return (d.month == 12 and d.day >= 27) or (d.month == 1 and d.day <= 2)
    if sid == "winter":
        return d.month in (12, 1, 2)
    a, b = window(sid, d.year)
    return a <= d <= b


def season(d):
    return next(s for s in ORDER if holds(s, d))


def rows():
    out = set()
    for y in YEARS:
        for sid in ("christmas", "mlkday", "valentines", "stpatricks", "easter", "mothersday", "fathersday", "julyfourth", "thanksgiving"):
            a, b = window(sid, y)
            for d in (a - D(1), a, b, b + D(1)):
                out.add((d.isoformat(), season(d)))
        for md in ((12, 26), (12, 27), (12, 31), (1, 1), (1, 2), (1, 3), (2, 28), (3, 1), (5, 31), (6, 1), (8, 31),
                   (9, 1), (9, 30), (10, 1), (10, 31), (11, 1), (11, 30)):
            d = dt.date(y, *md)
            out.add((d.isoformat(), season(d)))
    out.add(("2028-02-29", season(dt.date(2028, 2, 29))))
    return [list(r) for r in sorted(out)]


if __name__ == "__main__":
    path = Path(__file__).with_name("season-calendar.json")
    path.write_text(json.dumps(rows(), indent=0) + "\n", encoding="utf-8")
    print(len(rows()), "rows ->", path)
