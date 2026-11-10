"""Merge the 73 Tokyo candidates (POI-linked in 6 slices) into
data/tokyo_restaurants.csv as canonical, deduped rows.

Mirrors ~/workspace/taipei-eats/merge_desc.py, with Tokyo differences:
- Prices are JPY bands: 1 <1000, 2 1000-2500, 3 2500-5000, 4 5000+.
  Columns are price_min_jpy / price_max_jpy plus a currency=JPY column.
- Shared-like split reconstructed from the saved raw pages (same algorithm).
  Candidates also carry list_size when the split is known from extraction
  (the 29-name list comment; the 3-place maps-link comment) — the divisor
  is max(reconstructed count, list_size).
- Duplicates are NOT dropped silently: their adjusted mentions fold into
  the canonical row (yellow蛋包飯 +4 -> EDW; 鴨拉麵上野 +0 -> 鴨to蔥),
  with a note on the canonical row.
- popularity_score = round(mentions / max_mentions * 100), max = 423
  (佐藤養助 浅草店, the top single-comment count).
- district is the Tokyo neighborhood (浅草, 渋谷, ...); area is the street
  part of the address (ward stripped); mrt_station is the station name only.
- Asserts: no duplicate poi_key, id, or normalized name.
"""
import csv
import json
import os
import re
import unicodedata
from collections import Counter
from urllib.parse import quote

BASE = "/home/hatch/workspace/taipei-eats/data/tokyo"
CSV = "/home/hatch/workspace/taipei-eats/data/tokyo_restaurants.csv"
CAND = f"{BASE}/new_candidates_tokyo.json"
LINKS = [f"{BASE}/poi_links_tokyo_{s}.json" for s in "abcdef"]
RAW_DIR = f"{BASE}/raw_pages_desc"

BANDS = {1: (0, 1000), 2: (1000, 2500), 3: (2500, 5000), 4: (5000, 15000)}
LABELS = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}

FIELDS = ["id", "name", "name_en", "cuisine_primary", "cuisine_tags",
          "district", "area", "mrt_station", "price_level", "price_label",
          "price_min_jpy", "price_max_jpy", "currency", "must_try",
          "mentions", "popularity_score", "source", "maps_url", "notes",
          "added_at", "canonical_name", "poi_address", "poi_latitude",
          "poi_longitude", "poi_status", "poi_key", "poi_notes"]


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or "")).lower()


def norm_key_name(s: str) -> str:
    s = re.sub(r"[（(][^）)]*[）)]", "", s or "")
    return norm(s)


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKC", name).lower().replace("&", " and ")
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "poi"


def norm_tag(t: str) -> str:
    t = t.strip().lower().replace("_", "-").replace(" ", "-")
    t = re.sub(r"-+", "-", t)
    return {"dimsum": "dim-sum", "beef-noodle": "beef-noodles"}.get(t, t)


def street_of(address: str) -> str:
    # Strip the prefecture + ward/city prefix, keep the street part.
    return re.sub(r"^.*?[都道府県].*?[区市]", "", address or "")


def station_of(s: str) -> str:
    s = (s or "").split(" ")[0]
    return re.sub(r"[站駅]$", "", s)


def load_comments():
    comments = []
    for fn in sorted(os.listdir(RAW_DIR)):
        if not fn.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(RAW_DIR, fn), encoding="utf-8"))
        except Exception:
            continue
        for g in d.get("post_groups", []):
            for c in g.get("comments", []):
                comments.append(((c.get("comment_text") or ""),
                                 int(c.get("like_count") or 0)))
    return comments


def count_names_in(text: str, names_sorted) -> int:
    found, rest = set(), text
    for n in names_sorted:
        if n and n in rest:
            found.add(n)
            rest = rest.replace(n, " ")
    return len(found)


def main():
    cands = json.load(open(CAND, encoding="utf-8"))
    links = {}
    for f in LINKS:
        for r in json.load(open(f, encoding="utf-8")):
            links[r["name"]] = r
    assert len(links) == 73, f"links cover {len(links)}, expected 73"

    known = set()
    for c in cands:
        known.add(c["name"])
        if links.get(c["name"], {}).get("canonical_name"):
            known.add(links[c["name"]]["canonical_name"])
    known = {k for k in known if k}
    names_sorted = sorted(known, key=len, reverse=True)

    comments = load_comments()
    print(f"raw comments loaded: {len(comments)}")
    by_likes = {}
    for text, likes in comments:
        by_likes.setdefault(likes, []).append(text)

    rows, skipped, folds = [], [], []
    split_stats = Counter()
    existing_ids, existing_names, existing_keys = set(), set(), set()
    row_by_cand = {}

    def build_row(c, r, mentions):
        name = r["canonical_name"] or c["name"]
        rid = slug(name)
        base_rid, n = rid, 2
        while rid in existing_ids:
            rid, n = f"{base_rid}-{n}", n + 1
        tags = [norm_tag(t) for t in (r.get("cuisine_tags") or ["japanese"])]
        seen, uniq = set(), []
        for t in tags:
            if t not in seen:
                seen.add(t)
                uniq.append(t)
        level = int(r.get("price_level") or 2)
        lo, hi = BANDS[level]
        addr = r["verified_address"] or ""
        key = norm_key_name(name) + "|" + norm(addr)
        notes = [r.get("branch_notes") or "",
                 "price band estimated from price_level"]
        if c.get("_shared_note"):
            notes.append(c["_shared_note"])
        has_latin = bool(re.search(r"[A-Za-z]", name))
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", name))
        name_en = ""
        if has_latin and has_cjk:
            name_en = " ".join(w for w in re.split(r"\s+", name)
                               if re.search(r"[A-Za-z]", w))
        elif has_latin:
            name_en = name
        return {
            "id": rid, "name": name, "name_en": name_en,
            "cuisine_primary": uniq[0], "cuisine_tags": ";".join(uniq),
            "district": r["district"], "area": street_of(addr),
            "mrt_station": station_of(r.get("mrt_station")),
            "price_level": level, "price_label": LABELS[level],
            "price_min_jpy": lo, "price_max_jpy": hi, "currency": "JPY",
            "must_try": r.get("must_try") or "",
            "mentions": mentions, "popularity_score": 0,
            "source": "threads:rita611293-2026-06-12",
            "maps_url": ("https://www.google.com/maps/search/?api=1&query="
                         + quote(addr)),
            "notes": ("Seeded from Threads replies; prices are approximate "
                      "per-person JPY bands, verify before going."),
            "added_at": "2026-11-10",
            "canonical_name": name,
            "poi_address": addr,
            "poi_latitude": ("" if r.get("latitude") is None else str(r["latitude"])),
            "poi_longitude": ("" if r.get("longitude") is None else str(r["longitude"])),
            "poi_status": r["poi_status"],
            "poi_key": key,
            "poi_notes": " ".join(x for x in notes if x),
        }

    for c in cands:
        r = links[c["name"]]
        status = r["poi_status"]
        if status == "unmatched":
            skipped.append((c["name"], status, (r.get("evidence") or "")[:100]))
            continue
        if r.get("duplicate_of"):
            # Folded into the canonical row after the main loop.
            folds.append((c, r))
            continue
        name = r["canonical_name"] or c["name"]
        if norm(name) in existing_names:
            skipped.append((c["name"], "name-collision", f"matches {name}"))
            continue
        raw_mentions = int(c.get("mentions") or 0)
        divisor, mentions = 1, raw_mentions
        best = 1
        for text in by_likes.get(raw_mentions, []):
            if c["name"] in text or name in text:
                best = max(best, count_names_in(text, names_sorted))
        if c.get("list_size"):
            best = max(best, int(c["list_size"]))
        if best > 1:
            divisor = best
            mentions = round(raw_mentions / divisor)
            c["_shared_note"] = (f"shared-like split: {raw_mentions} likes "
                                 f"across {divisor} places in one comment")
            split_stats["split"] += 1
        else:
            split_stats["single"] += 1
        row = build_row(c, r, mentions)
        if row["poi_key"] in existing_keys:
            skipped.append((c["name"], "poi-key-collision", row["poi_key"]))
            continue
        rows.append(row)
        row_by_cand[c["name"]] = row
        existing_ids.add(row["id"])
        existing_names.add(norm(name))
        existing_keys.add(row["poi_key"])

    # Fold duplicate mentions into their canonical rows.
    for c, r in folds:
        target = r["duplicate_of"]
        trow = row_by_cand.get(target)
        if trow is None:
            # duplicate_of names a candidate; find its row by canonical name.
            for cand_name, row in row_by_cand.items():
                if row["name"] == target or cand_name == target:
                    trow = row
                    break
        if trow is None:
            skipped.append((c["name"], "duplicate-target-missing", target))
            continue
        raw = int(c.get("mentions") or 0)
        add = raw
        if c.get("list_size"):
            add = round(raw / int(c["list_size"]))
        trow["mentions"] += add
        trow["poi_notes"] += (f" +{add} likes folded from duplicate mention "
                             f"as {c['name']}.")
        skipped.append((c["name"], "duplicate-folded-into-" + trow["name"],
                        f"+{add} mentions"))

    max_m = max((row["mentions"] for row in rows), default=0)
    for row in rows:
        row["popularity_score"] = round(row["mentions"] / max_m * 100) if max_m else 0

    keys = [r["poi_key"] for r in rows]
    assert len(keys) == len(set(keys)), "duplicate poi_key"
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate id"
    names = [r["name"] for r in rows]
    assert len(names) == len(set(names)), "duplicate name"

    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"rows written: {len(rows)}")
    print("poi_status:", dict(Counter(r["poi_status"] for r in rows)))
    print("split stats:", dict(split_stats), "| max mentions:", max_m)
    print("top rows:", sorted([(r["mentions"], r["name"]) for r in rows], reverse=True)[:10])
    print("districts:", dict(Counter(r["district"] for r in rows).most_common(15)))
    print("skipped/folded:")
    for s in skipped:
        print("  ", s)


if __name__ == "__main__":
    main()
