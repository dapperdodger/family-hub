"""Tests for scripts/season-photo-search.py: the dev-only helper that finds public-domain / CC0 photo
candidates for seasonal looks. Pure functions only; the network is never touched here."""
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "sps", Path(__file__).resolve().parents[1] / "scripts" / "season-photo-search.py")
sps = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sps)


def test_only_public_domain_and_cc0_are_free():
    for ok in ("Public domain", "CC0", "CC0 1.0", "PD US Government", "PD-USGov-NPS", "Public domain (NASA)"):
        assert sps.is_free(ok), ok
    for bad in ("CC BY 4.0", "CC BY-SA 2.0", "CC BY-NC 4.0", "Unsplash License", "Pexels License", "",
                None, "All rights reserved", "Free to use", "Not public domain", "CC0-ish but not really"):
        assert not sps.is_free(bad), bad


def test_keep_wants_a_big_landscape_free_image():
    good = {"licence": "Public domain", "width": 4500, "height": 3000}
    assert sps.keep(good, 2560)
    assert not sps.keep({**good, "width": 1900}, 2560), "too small for the wall"
    assert not sps.keep({**good, "width": 3000, "height": 4500}, 2560), "portrait"
    assert not sps.keep({**good, "licence": "CC BY-SA 2.0"}, 2560), "not free"
    assert sps.keep({**good, "width": None}, 2560, allow_unknown_size=True)
    assert not sps.keep({**good, "width": None}, 2560)
    assert sps.keep({**good, "width": 3000, "height": 4500}, 2560, landscape=False), "portrait allowed on request"


COMMONS = {"query": {"pages": {"1": {"index": 1, "title": "File:Snow-covered pine forest (52599268392).jpg", "imageinfo": [{
    "url": "https://upload.example/orig.jpg", "thumburl": "https://upload.example/thumb.jpg", "width": 4500, "height": 3000,
    "descriptionurl": "https://commons.example/File:Snow",
    "extmetadata": {"LicenseShortName": {"value": "Public domain"},
                    "Artist": {"value": "<a href=\"x\">A. Photographer</a>"}}}]}}}}


def test_parse_commons_extracts_a_candidate_with_a_plain_creator():
    [c] = sps.parse_commons(COMMONS)
    assert c["source"] == "commons" and c["licence"] == "Public domain" and c["width"] == 4500
    assert c["creator"] == "A. Photographer", "markup stripped"
    assert c["page"].startswith("https://commons.") and c["thumb"].endswith("thumb.jpg")
    assert c["title"] == "Snow-covered pine forest (52599268392).jpg"


def test_parse_commons_survives_missing_fields():
    odd = {"query": {"pages": {"1": {"index": 1, "title": "File:X.jpg"}, "2": {"index": 2, "title": "File:Y.jpg", "imageinfo": [{}]}}}}
    out = sps.parse_commons(odd)
    assert [c["title"] for c in out] == ["Y.jpg"], "a page with no image info is skipped, an empty one tolerated"
    assert out[0]["creator"] == "unknown" and out[0]["licence"] is None
    assert sps.parse_commons({}) == []


def test_the_contact_sheet_escapes_everything_it_prints():
    html = sps.sheet_html([{"source": "commons", "id": "1", "title": "<script>x</script>", "creator": "\"><b>",
                            "licence": "CC0", "width": 4000, "height": 2000, "thumb": "https://t/x.jpg\" onerror=\"x",
                            "page": "https://p/x"}])
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert '"><b>' not in html and "&quot;&gt;&lt;b&gt;" in html, "a creator name cannot inject markup"
    assert 'onerror="x' not in html, "attribute values are escaped too"
    assert "CC0" in html and "4000" in html and "https://p/x" in html


def test_the_helper_never_touches_the_network_at_import_or_in_pure_functions(monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("network")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    sps.is_free("CC0")
    sps.keep({"licence": "CC0", "width": 3000, "height": 1500}, 2560)
    sps.parse_commons(COMMONS)
    sps.sheet_html([])


def test_the_search_command_keeps_only_free_big_landscape_results(tmp_path, monkeypatch):
    free = {"source": "commons", "id": "a", "title": "A", "creator": "c", "licence": "Public domain",
            "width": 4000, "height": 2000, "thumb": "t", "page": "p", "original": "o"}
    nonfree = {**free, "id": "b", "licence": "CC BY-SA 4.0"}
    small = {**free, "id": "c", "width": 1000, "height": 600}
    monkeypatch.setitem(sps.SOURCES, "commons", lambda q, n: [free, nonfree, small])
    sps.main(["search", "pines", "--out", str(tmp_path), "--sources", "commons"])
    import json
    kept = json.loads((tmp_path / "candidates.json").read_text())
    assert [c["id"] for c in kept] == ["a"]
    assert (tmp_path / "contact-sheet.html").read_text().count("<figure>") == 1


def test_one_source_failing_does_not_lose_the_others(tmp_path, monkeypatch, capsys):
    ok = {"source": "aic", "id": "1", "title": "T", "creator": "c", "licence": "Public domain (AIC, CC0)",
          "width": None, "height": None, "thumb": "t", "page": "p", "original": "o"}

    def down(q, n):
        raise OSError("down")
    monkeypatch.setitem(sps.SOURCES, "commons", down)
    monkeypatch.setitem(sps.SOURCES, "aic", lambda q, n: [ok])
    sps.main(["search", "x", "--out", str(tmp_path), "--sources", "commons,aic", "--allow-unknown-size"])
    assert "commons: OSError" in capsys.readouterr().err
    import json
    assert [c["id"] for c in json.loads((tmp_path / "candidates.json").read_text())] == ["1"]


def test_the_default_sources_are_ones_that_answer_and_all_satisfy_the_licence_rule():
    assert set(sps.SOURCES) == {"commons", "aic"}, "only sources verified to return results"
    import inspect
    src = inspect.getsource(sps)
    for banned in ("unsplash.com", "pexels.com", "pixabay.com"):
        assert banned not in src.replace("Unsplash, Pexels and Pixabay", ""), banned



def test_fetch_uses_the_user_agent_and_a_timeout_and_leaves_no_partial_file(tmp_path, monkeypatch, capsys):
    import io
    import json
    import urllib.request
    (tmp_path / "candidates.json").write_text(json.dumps([{"source": "commons", "id": "File:X.jpg", "title": "A | B", "creator": "C\nD",
                                                           "licence": "CC0", "page": "https://p/x", "original": "https://o/x.jpg"}]))
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        seen["timeout"] = timeout
        return Resp(b"JPEGDATA")
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    out = tmp_path / "pick.jpg"
    sps.main(["fetch", "commons:File:X.jpg", "--out", str(out)])
    assert out.read_bytes() == b"JPEGDATA" and not list(tmp_path.glob("*.part"))
    assert "family-hub-photo-search" in seen["ua"] and seen["timeout"] and seen["timeout"] > 0
    printed = capsys.readouterr().out
    assert "A \\| B" in printed and "C D" in printed, "a | or a newline in a title cannot break the CREDITS table"


def test_a_failed_download_leaves_nothing_behind_and_says_why(tmp_path, monkeypatch):
    import json
    import urllib.request
    import pytest
    (tmp_path / "candidates.json").write_text(json.dumps([{"source": "commons", "id": "a", "title": "T", "creator": "c",
                                                           "licence": "CC0", "page": "p", "original": "https://o/x.jpg"}]))

    def boom(req, timeout=None):
        raise OSError("403")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(SystemExit) as e:
        sps.main(["fetch", "commons:a", "--out", str(tmp_path / "pick.jpg")])
    assert "OSError" in str(e.value)
    assert not list(tmp_path.glob("pick*")), "no partial file"


def test_a_download_that_breaks_half_way_leaves_no_partial_photo(tmp_path, monkeypatch):
    import io
    import json
    import urllib.request
    import pytest
    (tmp_path / "candidates.json").write_text(json.dumps([{"source": "commons", "id": "a", "title": "T", "creator": "c",
                                                           "licence": "CC0", "page": "p", "original": "https://o/x.jpg"}]))

    class Half(io.RawIOBase):
        def __init__(self):
            self.sent = False

        def readable(self):
            return True

        def readinto(self, b):
            if not self.sent:
                self.sent = True
                b[:4] = b"JPEG"
                return 4
            raise OSError("connection reset")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: Half())
    with pytest.raises(SystemExit) as e:
        sps.main(["fetch", "commons:a", "--out", str(tmp_path / "pick.jpg")])
    assert "connection reset" in str(e.value)
    assert not list(tmp_path.glob("pick*")), "neither the photo nor its .part file is left"
