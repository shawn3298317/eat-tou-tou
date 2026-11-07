"""Checkpoint helper for the batch-2 desc crawl.

Usage: python3 checkpoint_page.py <page_number> <candidates_json_file> [stopped_reason]

- Appends the candidates (deduped by normalized name) to
  ~/workspace/taipei-eats/data/new_candidates_desc.json
- Updates ~/workspace/taipei-eats/data/crawl_progress_desc.json from the
  raw page file's end_cursor and last comment date.
"""
import json
import re
import sys
import unicodedata

BASE = "/home/hatch/workspace/taipei-eats/data"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or "")).lower()


def main():
    page = int(sys.argv[1])
    cand_file = sys.argv[2]
    stopped = sys.argv[3] if len(sys.argv) > 3 else ""
    new = json.load(open(cand_file, encoding="utf-8"))
    raw = json.load(open(f"{BASE}/raw_pages_desc/page_desc_{page:02d}.json", encoding="utf-8"))
    g = raw["post_groups"][0]
    desc_path = f"{BASE}/new_candidates_desc.json"
    existing = json.load(open(desc_path, encoding="utf-8"))
    names = {norm(c["name"]) for c in existing}
    added = 0
    for c in new:
        if norm(c["name"]) not in names:
            existing.append(c)
            names.add(norm(c["name"]))
            added += 1
    with open(desc_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    prog_path = f"{BASE}/crawl_progress_desc.json"
    prog = json.load(open(prog_path, encoding="utf-8"))
    prog.update({
        "pages_done": page,
        "last_cursor": g["end_cursor"],
        "last_comment_date": g["comments"][-1]["created_at"],
        "candidates_so_far": len(existing),
        "stopped_reason": stopped,
    })
    with open(prog_path, "w", encoding="utf-8") as f:
        json.dump(prog, f, ensure_ascii=False, indent=2)
    print(f"page {page} checkpointed: +{added} new, total {len(existing)}, "
          f"last_date {prog['last_comment_date']}, stopped={stopped!r}")


if __name__ == "__main__":
    main()
