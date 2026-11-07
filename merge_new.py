"""Merge the 124 new thread candidates (POI-linked in 3 slices) into
data/restaurants.csv as canonical, deduped rows.

Rules:
- Only poi_status matched / address_only rows are added. unmatched and
  duplicate rows are skipped and reported.
- Shared-like split (only for the two list-comments the expansion agent
  confirmed): the 491-like list named 11 restaurants -> each gets
  round(491/11)=45 mentions; the 78-like list named 14 -> round(78/14)=6.
  All other mentions are kept raw. popularity_score = round(mentions/844*100)
  (844 = Sunami, the max, same formula as the original 44).
- price_min/max are band bounds from price_level (flagged in poi_notes as
  estimated); the original rows keep their parsed ranges.
- id is a slug of the canonical name; CJK names keep their characters.
- Asserts: no duplicate poi_key, id, or normalized name across old + new.
"""
import csv
import json
import re
import unicodedata
from collections import Counter
from urllib.parse import quote

BASE = "/home/hatch/workspace/taipei-eats"
CSV = f"{BASE}/data/restaurants.csv"
CAND = f"{BASE}/data/new_candidates.json"
LINKS = [f"{BASE}/data/poi_links_new_{s}.json" for s in "abc"]

BANDS = {1: (0, 300), 2: (300, 700), 3: (700, 1500), 4: (1500, 5000)}
LABELS = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
TAG_FIX = {"ice": "dessert"}  # shaved-ice shops are dessert
SHARED = {491: 11, 78: 14}    # comment likes -> number of restaurants listed


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or "")).lower()


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKC", name).lower().replace("&", " and ")
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "poi"


def street_of(address: str) -> str:
    return re.sub(r"^(?:台北市|新北市)[^區]+區", "", address or "")


def main():
    with open(CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())
    cands = json.load(open(CAND, encoding="utf-8"))
    links = {}
    for path in LINKS:
        for r in json.load(open(path, encoding="utf-8")):
            assert r["name"] not in links, f"dup link row: {r['name']}"
            links[r["name"]] = r
    assert len(cands) == 124 and len(links) == 124, (len(cands), len(links))
    missing = [c["name"] for c in cands if c["name"] not in links]
    assert not missing, missing

    existing_keys = {r["poi_key"] for r in rows if r.get("poi_key")}
    existing_ids = {r["id"] for r in rows}
    existing_names = {norm(r["name"]) for r in rows} | {
        norm(r.get("canonical_name", "")) for r in rows}
    all_tags = Counter()
    added, skipped = [], []
    for c in cands:
        r = links[c["name"]]
        status = r["poi_status"]
        if status in ("unmatched", "duplicate"):
            skipped.append((c["name"], status,
                            (r.get("branch_notes") or "")[:100]))
            continue
        name = r["canonical_name"] or c["name"]
        if norm(name) in existing_names:
            skipped.append((c["name"], "name-collision", f"matches {name}"))
            continue
        rid = slug(name)
        base_rid, n = rid, 2
        while rid in existing_ids:
            rid, n = f"{base_rid}-{n}", n + 1
        tags = [TAG_FIX.get(t, t) for t in (r.get("cuisine_tags") or ["taiwanese"])]
        all_tags.update(tags)
        raw_mentions = int(c.get("mentions") or 0)
        if raw_mentions in SHARED:
            mentions = round(raw_mentions / SHARED[raw_mentions])
            shared_note = (f"shared-like split: {raw_mentions} likes across "
                           f"{SHARED[raw_mentions]} places in one comment")
        else:
            mentions, shared_note = raw_mentions, ""
        level = int(r.get("price_level") or 2)
        lo, hi = BANDS[level]
        addr = r["verified_address"]
        key = norm(name) + "|" + norm(addr)
        if key in existing_keys:
            skipped.append((c["name"], "poi-key-collision", key))
            continue
        notes = [r.get("branch_notes") or "",
                 "price band estimated from price_level", shared_note]
        has_latin = bool(re.search(r"[A-Za-z]", name))
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", name))
        name_en = ""
        if has_latin and has_cjk:
            name_en = " ".join(w for w in re.split(r"\s+", name) if re.search(r"[A-Za-z]", w))
        elif has_latin:
            name_en = name
        row = {
            "id": rid, "name": name, "name_en": name_en,
            "cuisine_primary": tags[0], "cuisine_tags": ";".join(tags),
            "district": r["district"], "area": street_of(addr),
            "mrt_station": (r.get("mrt_station") or "").rstrip("站"),
            "price_level": level, "price_label": LABELS[level],
            "price_min_ntd": lo, "price_max_ntd": hi,
            "must_try": r.get("must_try") or "",
            "mentions": mentions,
            "popularity_score": round(mentions / 844 * 100),
            "source": "threads:harriet0308-2026-07-19",
            "maps_url": ("https://www.google.com/maps/search/?api=1&query="
                         + quote(addr)),
            "notes": "Seeded from Threads replies; prices are approximate "
                     "per-person bands, verify before going.",
            "added_at": "2026-11-07",
            "canonical_name": name,
            "poi_address": addr,
            "poi_latitude": str(r["latitude"]),
            "poi_longitude": str(r["longitude"]),
            "poi_status": status,
            "poi_key": key,
            "poi_notes": " ".join(x for x in notes if x),
        }
        rows.append(row)
        added.append(row)
        existing_keys.add(key)
        existing_ids.add(rid)
        existing_names.add(norm(name))

    # Final dedupe assertions over the whole file.
    keys = [r["poi_key"] for r in rows if r.get("poi_key")]
    assert len(keys) == len(set(keys)), "duplicate poi_key in merged file"
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate id in merged file"

    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"added: {len(added)}  skipped: {len(skipped)}  total rows: {len(rows)}")
    print("skipped:")
    for name, why, detail in skipped:
        print(f"  - {name} [{why}] {detail}")
    print("poi_status:", dict(Counter(r["poi_status"] for r in rows)))
    print("districts:", dict(Counter(r["district"] for r in rows)))
    print("new cuisine tags:", dict(all_tags))
    top = sorted(added, key=lambda r: -r["mentions"])[:8]
    print("top new by mentions:", [(r["name"], r["mentions"]) for r in top])


if __name__ == "__main__":
    main()
