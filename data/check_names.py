"""Check candidate names against everything already known (CSV + all
candidate files), with substring matching both ways.

Usage: python3 check_names.py '["name1", "name2", ...]'
Prints NEW: or KNOWN: per name, with the matching known name(s).
"""
import csv
import json
import re
import sys
import unicodedata

BASE = "/home/hatch/workspace/taipei-eats/data"


def norm(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or "")).lower()


def main():
    known = {}  # normalized -> display name
    with open(f"{BASE}/restaurants.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for key in (r.get("name"), r.get("canonical_name")):
                if key:
                    known.setdefault(norm(key), key)
    for fn in ("new_candidates.json", "new_candidates_desc.json",
               "new_candidates_asc.json"):
        try:
            for o in json.load(open(f"{BASE}/{fn}", encoding="utf-8")):
                if o.get("name"):
                    known.setdefault(norm(o["name"]), o["name"])
        except FileNotFoundError:
            pass
    names = json.loads(sys.argv[1])
    for n in names:
        nn = norm(n)
        hits = sorted({disp for k, disp in known.items()
                       if k and len(k) >= 2 and len(nn) >= 2 and (k in nn or nn in k)})
        if hits:
            print(f"KNOWN: {n}  ~ {hits[:4]}")
        else:
            print(f"NEW:   {n}")


if __name__ == "__main__":
    main()
