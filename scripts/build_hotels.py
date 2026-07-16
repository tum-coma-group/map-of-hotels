#!/usr/bin/env python3
"""Build hotels.js from the Bavarian hotel-list .xlsx.

Parses the spreadsheet (stdlib only — an .xlsx is a zip of XML), keeps the real
hotel rows, normalizes whitespace, geocodes each address via the free OpenStreetMap
Nominatim API, and writes `hotels.js` (window.HOTELS = [...]).

Re-run this whenever the source spreadsheet changes:

    python scripts/build_hotels.py

Geocoding is rate-limited to ~1 request/second per Nominatim's usage policy, so a
full run of ~400 hotels takes several minutes. Results are cached in
scripts/geocode_cache.json so re-runs are fast and don't re-hit the API.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
XLSX = os.path.join(ROOT, "2025_Hotelliste_Freistaat_ByBn_Inland.xlsx")
OUT = os.path.join(ROOT, "hotels.js")
CACHE = os.path.join(HERE, "geocode_cache.json")

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "hotel-map-viewer/1.0 (static map build script)"

# Spreadsheet column letter -> output key. Header is row 4; data starts row 5.
COLUMNS = {
    "B": "stadt",
    "C": "hotel",
    "D": "adresse",
    "E": "plz",
    "F": "email",
    "G": "telefon",
    "H": "ez",
    "I": "dz",
    "J": "stornierung",
    "K": "buchungscode",
    "L": "gueltig_bis",
    "M": "bemerkung",
    "N": "nachhaltigkeit",
}


# Source-spreadsheet quirks: city names split across lines or misspelled.
# Applied to the STADT field so geocoding can find them.
CITY_FIXES = {
    "Braun- schweig": "Braunschweig",
    "Saarrbrücken": "Saarbrücken",
    "Halbergmoos": "Hallbergmoos",
}


def norm(s):
    """Collapse internal whitespace/newlines and strip."""
    if s is None:
        return ""
    return " ".join(str(s).split()).strip()


def fix_city(stadt):
    return CITY_FIXES.get(stadt, stadt)


def parse_xlsx(path):
    z = zipfile.ZipFile(path)
    shared = [
        "".join(t.text or "" for t in si.iter(NS + "t"))
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(NS + "si")
    ]
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = sheet.find(NS + "sheetData").findall(NS + "row")

    def cell_value(c):
        t = c.get("t")
        v = c.find(NS + "v")
        inline = c.find(NS + "is")
        if t == "s" and v is not None:
            return shared[int(v.text)]
        if t == "inlineStr" and inline is not None:
            return "".join(x.text or "" for x in inline.iter(NS + "t"))
        return v.text if v is not None else ""

    def col_of(ref):
        return "".join(ch for ch in ref if ch.isalpha())

    hotels = []
    for i, row in enumerate(rows):
        if i < 4:  # skip title/intro/header rows (rows 1-4)
            continue
        cells = {col_of(c.get("r")): cell_value(c) for c in row.findall(NS + "c")}
        if not norm(cells.get("C")):  # no hotel name -> city divider row, skip
            continue
        hotel = {key: norm(cells.get(letter, "")) for letter, key in COLUMNS.items()}
        hotel["stadt"] = fix_city(hotel["stadt"])
        hotels.append(hotel)
    return hotels


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


def nominatim(query):
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    req = urllib.request.Request(
        NOMINATIM + "?" + params, headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data:
        return float(data[0]["lat"]), float(data[0]["lon"])
    return None


def geocode(hotel, cache):
    """Return (lat, lng) or None. Tries full address, then PLZ + city."""
    full = f"{hotel['adresse']}, {hotel['plz']} {hotel['stadt']}, Germany"
    fallback = f"{hotel['plz']} {hotel['stadt']}, Germany"
    for query in (full, fallback):
        if query in cache:
            result = cache[query]
        else:
            try:
                result = nominatim(query)
            except Exception as e:  # noqa: BLE001 - log and continue
                print(f"  ! request error for {query!r}: {e}", file=sys.stderr)
                result = None
            cache[query] = result
            save_cache(cache)
            time.sleep(1.1)  # respect Nominatim's 1 req/sec policy
        if result:
            return result
    return None


def main():
    if not os.path.exists(XLSX):
        sys.exit(f"Source spreadsheet not found: {XLSX}")

    hotels = parse_xlsx(XLSX)
    print(f"Parsed {len(hotels)} hotel rows.")

    cache = load_cache()
    failures = []
    for i, hotel in enumerate(hotels, 1):
        coords = geocode(hotel, cache)
        if coords:
            hotel["lat"], hotel["lng"] = coords
        else:
            hotel["lat"], hotel["lng"] = None, None
            failures.append(hotel)
        if i % 25 == 0 or i == len(hotels):
            print(f"  geocoded {i}/{len(hotels)} ({len(failures)} failed)")

    located = [h for h in hotels if h["lat"] is not None]
    banner = (
        "// AUTO-GENERATED by scripts/build_hotels.py - do not edit by hand.\n"
        "// Source: 2025_Hotelliste_Freistaat_ByBn_Inland.xlsx\n"
    )
    body = "window.HOTELS = " + json.dumps(located, ensure_ascii=False, indent=2) + ";\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(banner + body)

    print(f"\nWrote {len(located)} hotels with coordinates to {OUT}")
    if failures:
        print(f"\n{len(failures)} hotels FAILED to geocode (excluded from map):")
        for h in failures:
            print(f"  - {h['hotel']} | {h['adresse']}, {h['plz']} {h['stadt']}")
        print("\nReview these: fix the address/city in the spreadsheet, or add a manual")
        print("coordinate. Re-run after fixing (cached successes will not re-hit the API).")


if __name__ == "__main__":
    main()
