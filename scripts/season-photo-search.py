#!/usr/bin/env python3
"""Search open sources for seasonal-look photo candidates (dev-only, stdlib only).

    python scripts/season-photo-search.py search "snow covered pine forest" --out scratch/winter [--min-width 2560]
    python scripts/season-photo-search.py fetch commons:File:Snow-covered_pine_forest_(52599268392).jpg --out scratch/winter/pick.jpg

Only sources that satisfy docs/seasonal-looks.md section 5 are searched: Wikimedia Commons (public domain and
CC0 files, which includes NPS and NASA works) and the Art Institute of Chicago (filtered to public domain). The current Unsplash, Pexels and Pixabay licences are NOT used (operator decision
2026-10-06). `search` writes contact-sheet.html and candidates.json; nothing is downloaded until `fetch`.

After picking: `fetch` the original, run scripts/prep-season-photo.py on it, add the CREDITS.md row that `fetch`
prints, and judge the photo by eye behind the glass cards on the wall (the standard says how).
"""
import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

UA = {"User-Agent": "family-hub-photo-search/0.1 (dev tool; public-domain search)"}
# "Public domain", "CC0" / "CC0 1.0", "PD US Government", "PD-USGov-NPS": nothing else is free here
FREE = re.compile(r"^(cc0(\s+1\.0)?(\s|$)|public domain\b|pd[ -])", re.I)


def is_free(licence):
    return bool(licence) and bool(FREE.match(str(licence).strip()))


def keep(c, min_width, landscape=True, allow_unknown_size=False):
    if not is_free(c.get("licence")):
        return False
    w, h = c.get("width"), c.get("height")
    if not w or not h:
        return allow_unknown_size
    if w < min_width:
        return False
    return (w >= h * 1.3) if landscape else True


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def _plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def parse_commons(payload):
    out = []
    pages = (payload.get("query") or {}).get("pages") or {}
    for pg in sorted(pages.values(), key=lambda p: p.get("index", 0)):
        info = (pg.get("imageinfo") or [None])[0]
        if info is None:
            continue
        meta = info.get("extmetadata") or {}
        out.append({"source": "commons", "id": pg["title"], "title": pg["title"].removeprefix("File:"),
                    "creator": _plain((meta.get("Artist") or {}).get("value")) or "unknown",
                    "licence": (meta.get("LicenseShortName") or {}).get("value"),
                    "width": info.get("width"), "height": info.get("height"),
                    "thumb": info.get("thumburl"), "page": info.get("descriptionurl"), "original": info.get("url")})
    return out


def search_commons(query, limit):
    p = {"action": "query", "format": "json", "generator": "search", "gsrsearch": query + " filetype:bitmap",
         "gsrnamespace": "6", "gsrlimit": str(limit), "prop": "imageinfo", "iiprop": "url|size|extmetadata",
         "iiurlwidth": "480", "iiextmetadatafilter": "LicenseShortName|Artist"}
    return parse_commons(_get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(p)))


def search_aic(query, limit):
    d = _get("https://api.artic.edu/api/v1/artworks/search?" + urllib.parse.urlencode(
        {"q": query, "limit": str(limit), "fields": "id,title,artist_display,image_id,is_public_domain,thumbnail",
         "query[term][is_public_domain]": "true"}))
    out = []
    for a in d.get("data", []):
        if a.get("is_public_domain") and a.get("image_id"):
            iiif = f"https://www.artic.edu/iiif/2/{a['image_id']}"
            th = a.get("thumbnail") or {}
            out.append({"source": "aic", "id": str(a["id"]), "title": a.get("title", ""),
                        "creator": a.get("artist_display") or "unknown",
                        "licence": "Public domain (AIC, CC0)", "width": th.get("width"), "height": th.get("height"),
                        "thumb": f"{iiif}/full/400,/0/default.jpg", "page": f"https://www.artic.edu/artworks/{a['id']}",
                        "original": f"{iiif}/full/full/0/default.jpg"})
    return out


# The Met's public search endpoint answers 410 Gone (checked 2026-10-06), so it is not searched; add a source here
# only after a real query returns results.
SOURCES = {"commons": search_commons, "aic": search_aic}


def sheet_html(cands):
    e = lambda v: html.escape(str(v if v is not None else ""), quote=True)    # noqa: E731 (one-liner on purpose)
    cards = "".join(
        f'<figure><a href="{e(c.get("page"))}"><img src="{e(c.get("thumb"))}" alt=""></a>'
        f'<figcaption><b>{e(c.get("title"))}</b><br>{e(c.get("creator"))}<br>{e(c.get("licence"))} &middot; '
        f'{e(c.get("width") or "?")} x {e(c.get("height") or "?")}<br><code>{e(c.get("source"))}:{e(c.get("id"))}</code></figcaption></figure>'
        for c in cands)
    return ("<!doctype html><meta charset=utf-8><title>Season photo candidates</title><style>"
            "body{font:14px system-ui;background:#111;color:#ddd;margin:16px}"
            "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}"
            "figure{margin:0}img{width:100%;aspect-ratio:16/9;object-fit:cover;background:#222}"
            "figcaption{padding:6px 0}a{color:#9cf}</style><main>" + cards + "</main>")


def cmd_search(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    found = []
    for name in a.sources.split(","):
        try:
            found += SOURCES[name](a.query, a.limit)
        except Exception as ex:                       # one source being down must not lose the others
            print(f"{name}: {type(ex).__name__}: {ex}", file=sys.stderr)
    kept = [c for c in found if keep(c, a.min_width, allow_unknown_size=a.allow_unknown_size)]
    (out / "candidates.json").write_text(json.dumps(kept, indent=2), encoding="utf-8")
    (out / "contact-sheet.html").write_text(sheet_html(kept), encoding="utf-8")
    print(f"{len(found)} found, {len(kept)} kept (free licence, landscape, >= {a.min_width}px) -> {out / 'contact-sheet.html'}")


def cmd_fetch(a):
    source, _, ident = a.ref.partition(":")
    listing = Path(a.out).parent / "candidates.json"
    if not listing.is_file():
        sys.exit(f"no candidates.json next to {a.out} (run `search --out <that folder>` first)")
    cand = next((c for c in json.loads(listing.read_text(encoding="utf-8"))
                 if c["source"] == source and c["id"] == ident), None)
    if not cand:
        sys.exit(f"{a.ref} is not in {listing}")
    urllib.request.urlretrieve(cand["original"], a.out)
    print(f"saved {a.out}\nCREDITS.md row:\n| {Path(a.out).name} | {cand['title']} by {cand['creator']} | "
          f"{cand['page']} | {cand['licence']} | resized to 2560px, metadata stripped |")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--out", required=True)
    s.add_argument("--sources", default="commons,aic")
    s.add_argument("--min-width", type=int, default=2560)
    s.add_argument("--limit", type=int, default=24)
    s.add_argument("--allow-unknown-size", action="store_true", help="keep art results whose size the API does not give")
    s.set_defaults(fn=cmd_search)
    f = sub.add_parser("fetch")
    f.add_argument("ref", help="SOURCE:ID exactly as shown on the contact sheet")
    f.add_argument("--out", required=True)
    f.set_defaults(fn=cmd_fetch)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
