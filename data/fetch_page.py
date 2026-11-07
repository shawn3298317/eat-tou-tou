"""Fetch one desc page of thread comments and save the raw JSON.

Usage: python3 fetch_page.py <page_number> <cursor>
Prints a compact comment listing for extraction, plus END_CURSOR_FULL.
On a 429 or any fetch failure it prints {"status": "error", ...} and does
NOT write a raw file. Stderr is reported in the output (never a sidecar).
"""
import json
import re
import subprocess
import sys

BASE = "/home/hatch/workspace/taipei-eats/data"
POST_ID = "18113719412301018"
ACCOUNT_ID = "17841462905728526"


def main():
    page = int(sys.argv[1])
    cursor = sys.argv[2]
    cmd = ["/opt/hatch/bin/threads-cli", "fetch-post-comments",
           "--post-ids", POST_ID,
           "--sort-order", "desc", "--limit", "50",
           "--after", cursor,
           "--account-id", ACCOUNT_ID]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    # Save the raw stdout first so a detection mistake never loses a page.
    tmp_path = f"/tmp/fetch_page_{page}.stdout"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(r.stdout or "")
    # A bare "429" substring is NOT a rate limit: fbids and other numeric
    # IDs routinely contain those digits. Only explicit error markers count.
    err_text = r.stderr or ""
    if re.search(r"\b429\b", err_text) or (
            "rate" in err_text.lower() and "limit" in err_text.lower()):
        print(json.dumps({"status": "error", "kind": "rate_limited",
                          "returncode": r.returncode,
                          "stderr": err_text[:1500],
                          "stdout_head": (r.stdout or "")[:300]}))
        return
    if r.returncode != 0:
        print(json.dumps({"status": "error", "kind": "fetch_failed",
                          "returncode": r.returncode,
                          "stderr": err_text[:1500],
                          "stdout_head": (r.stdout or "")[:300]}))
        return
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        print(json.dumps({"status": "error", "kind": "bad_json",
                          "stdout_head": (r.stdout or "")[:500]}))
        return
    if isinstance(data, dict) and data.get("error"):
        print(json.dumps({"status": "error", "kind": "api_error",
                          "error": str(data["error"])[:500]}))
        return
    groups = data.get("post_groups") or []
    if not groups:
        print(json.dumps({"status": "error", "kind": "no_groups",
                          "stderr": (r.stderr or "")[:500]}))
        return
    g = groups[0]
    if g.get("error"):
        print(json.dumps({"status": "error", "kind": "group_error",
                          "error": str(g["error"])[:500]}))
        return
    out_path = f"{BASE}/raw_pages_desc/page_desc_{page:02d}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    comments = g.get("comments") or []
    print(f"PAGE {page}: {len(comments)} comments, "
          f"has_next={g.get('has_next_page')}, total={g.get('total_count')}")
    if comments:
        print("FIRST_DATE:", comments[0].get("created_at"))
        print("LAST_DATE:", comments[-1].get("created_at"))
    for i, c in enumerate(comments):
        text = (c.get("comment_text") or "").replace("\n", " / ")
        print(f"[{i}] likes={c.get('like_count')} "
              f"{c.get('created_at')} :: {text}")
    print("END_CURSOR_FULL:", g.get("end_cursor") or "")
    print("RAW_SAVED:", out_path)


if __name__ == "__main__":
    main()
