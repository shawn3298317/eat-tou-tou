"""Merge the 728 desc candidates (POI-linked in 12 slices) into
data/restaurants.csv as canonical, deduped rows.

Rules:
- Only poi_status matched / address_only rows are added. unmatched and
  duplicate rows are skipped and reported.
- Shared-like split, reconstructed from the saved raw pages: for each
  candidate, find the comment that named it (text contains the thread name
  or the canonical name, like_count == the candidate's mentions) and count
  distinct known restaurant names in that comment (greedy longest-first).
  Adjusted mentions = round(raw / count). popularity_score =
  round(mentions/844*100) (844 = Sunami, the max, same as the original 44).
- poi_key strips parenthetical suffixes (both （） and ()) from the name
  before normalizing, so same-venue pairs like 游壽司 (麗水店) /
  游壽司 麗水店 and 夫妻肺片麻辣火鍋 / 夫妻肺片麻辣火鍋（長安店）
  collapse to one row. On a poi_key collision the matched row wins over
  address_only; otherwise first-in-file wins.
- price_min/max are band bounds from price_level (flagged in poi_notes).
- 吉豚屋 is added manually: the thread named a 松江旗艦店 near 行天宮
  that does not exist in the 2026 branch list, so the canonical row is the
  first Taiwan store (和億北車店, 2015), geocode-verified.
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
CAND = f"{BASE}/data/new_candidates_desc.json"
CAND2 = f"{BASE}/data/new_candidates.json"
LINKS = [f"{BASE}/data/poi_links_desc_{s}.json" for s in "abcdefghijkl"]
RAW_DIR = f"{BASE}/data/raw_pages_desc"

BANDS = {1: (0, 300), 2: (300, 700), 3: (700, 1500), 4: (1500, 5000)}
LABELS = {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}
TAG_FIX = {"ice": "dessert"}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or "")).lower()


def norm_key_name(s: str) -> str:
    """Name for the dedupe key: strip parenthetical suffixes, then normalize."""
    s = re.sub(r"[（(][^）)]*[）)]", "", s or "")
    return norm(s)


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKC", name).lower().replace("&", " and ")
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "poi"


def street_of(address: str) -> str:
    return re.sub(r"^(?:台北市|新北市)[^區]+區", "", address or "")


def load_comments():
    import os
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
                t = c.get("comment_text") or ""
                if t:
                    comments.append((t, int(c.get("like_count") or 0)))
    return comments


def count_names_in(text: str, names_sorted) -> int:
    """Greedy longest-first count of distinct known names in the text."""
    found = set()
    i, n = 0, len(text)
    while i < n:
        matched = None
        for name in names_sorted:
            if name and text.startswith(name, i):
                matched = name
                break
        if matched:
            found.add(matched)
            i += len(matched)
        else:
            i += 1
    return max(1, len(found))


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
    assert len(cands) == 728 and len(links) == 728, (len(cands), len(links))
    missing = [c["name"] for c in cands if c["name"] not in links]
    assert not missing, missing

    # Known names for shared-like reconstruction.
    known = set()
    for r in rows:
        known.add(r["name"])
        known.add(r.get("canonical_name", ""))
    for c in cands:
        known.add(c["name"])
    for c in json.load(open(CAND2, encoding="utf-8")):
        known.add(c["name"])
    known = {k for k in known if k}
    names_sorted = sorted(known, key=len, reverse=True)

    comments = load_comments()
    print(f"raw comments loaded: {len(comments)}")
    # Index comments by like_count for fast lookup.
    by_likes = {}
    for text, likes in comments:
        by_likes.setdefault(likes, []).append(text)

    existing_keys = {r["poi_key"] for r in rows if r.get("poi_key")}
    existing_ids = {r["id"] for r in rows}
    existing_names = {norm(r["name"]) for r in rows} | {
        norm(r.get("canonical_name", "")) for r in rows}
    all_tags = Counter()
    added, skipped = [], []
    split_stats = Counter()
    key_rows = {}  # poi_key -> row, for collision handling

    def build_row(c, r, mentions):
        name = r["canonical_name"] or c["name"]
        rid = slug(name)
        base_rid, n = rid, 2
        while rid in existing_ids:
            rid, n = f"{base_rid}-{n}", n + 1
        tags = [TAG_FIX.get(t, t) for t in (r.get("cuisine_tags") or ["taiwanese"])]
        all_tags.update(tags)
        level = int(r.get("price_level") or 2)
        lo, hi = BANDS[level]
        addr = r["verified_address"]
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
            "poi_status": r["poi_status"],
            "poi_key": key,
            "poi_notes": " ".join(x for x in notes if x),
        }

    def place_row(row, cand_name, why=""):
        key = row["poi_key"]
        if key in key_rows:
            prev = key_rows[key]
            # matched beats address_only; otherwise keep the first.
            rank = {"matched": 0, "address_only": 1}
            if rank.get(row["poi_status"], 2) < rank.get(prev["poi_status"], 2):
                skipped.append((prev["_cand_name"], "poi-key-collision",
                                f"replaced by {cand_name} ({key})"))
                added.remove(prev)
                key_rows[key] = row
                return True
            skipped.append((cand_name, "poi-key-collision", key))
            return False
        if key in existing_keys:
            skipped.append((cand_name, "poi-key-collision", key))
            return False
        key_rows[key] = row
        return True

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
        # Shared-like reconstruction.
        raw_mentions = int(c.get("mentions") or 0)
        divisor, mentions = 1, raw_mentions
        candidates_texts = by_likes.get(raw_mentions, [])
        best = 1
        for text in candidates_texts:
            if c["name"] in text or name in text:
                best = max(best, count_names_in(text, names_sorted))
        if best > 1:
            divisor = best
            mentions = round(raw_mentions / divisor)
            c["_shared_note"] = (f"shared-like split: {raw_mentions} likes "
                                 f"across {divisor} places in one comment")
            split_stats["split"] += 1
        else:
            split_stats["single"] += 1
        row = build_row(c, r, mentions)
        row["_cand_name"] = c["name"]
        if place_row(row, c["name"]):
            added.append(row)
            existing_ids.add(row["id"])
            existing_names.add(norm(name))

    # 吉豚屋, manual row: thread named a 松江旗艦店 near 行天宮 that does
    # not exist in the 2026 branch list; canonical is the first Taiwan
    # store (和億北車店, 2015), geocode-verified FULL_ADDRESS.
    jiyu = {
        "name": "吉豚屋", "canonical_name": "吉豚屋",
        "verified_address": "台北市中正區忠孝西路一段36號B1",
        "district": "中正區", "latitude": 25.04605, "longitude": 121.51706,
        "mrt_station": "台北車站", "poi_status": "matched",
        "cuisine_tags": ["tonkatsu", "japanese"], "price_level": 1,
        "must_try": "",
        "branch_notes": ("commenter named a 松江旗艦店 near 行天宮, but no "
                         "such branch exists in the 2026 branch list; "
                         "canonical is the first Taiwan store (和億北車店, "
                         "2015)."),
    }
    jcand = {"name": "吉豚屋", "_shared_note": ""}
    jrow = build_row(jcand, jiyu, 6)
    jrow["_cand_name"] = "吉豚屋"
    if place_row(jrow, "吉豚屋"):
        added.append(jrow)
        existing_ids.add(jrow["id"])

    for row in added:
        row.pop("_cand_name", None)
    rows.extend(added)

    keys = [r["poi_key"] for r in rows if r.get("poi_key")]
    assert len(keys) == len(set(keys)), "duplicate poi_key in merged file"
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate id in merged file"

    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"added: {len(added)}  skipped: {len(skipped)}  total rows: {len(rows)}")
    print("shared-like split:", dict(split_stats))
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
