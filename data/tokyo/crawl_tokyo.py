"""Sequential desc crawl for the Tokyo thread (post 17933740629270328).
Pages 2..N, 90s between calls, checkpoint raw JSON + progress after EVERY page.
Stops on first 429 / fetch failure / has_next_page False. Never retries a 429.
Usage: python3 crawl_tokyo.py   (resumes from crawl_progress_desc.json cursor)
"""
import json, re, subprocess, sys, time

BASE = "/home/hatch/workspace/taipei-eats/data/tokyo"
POST_ID = "17933740629270328"
ACCOUNT_ID = "17841462905728526"
PROG = f"{BASE}/crawl_progress_desc.json"

def fetch_page(page, cursor):
    cmd = ["/opt/hatch/bin/threads-cli", "fetch-post-comments",
           "--post-ids", POST_ID, "--sort-order", "desc", "--limit", "50",
           "--after", cursor, "--account-id", ACCOUNT_ID]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    err_text = r.stderr or ""
    if re.search(r"\b429\b", err_text) or ("rate" in err_text.lower() and "limit" in err_text.lower()):
        return {"status": "error", "kind": "rate_limited", "stderr": err_text[:1500]}
    if r.returncode != 0:
        return {"status": "error", "kind": "fetch_failed", "returncode": r.returncode, "stderr": err_text[:1500]}
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "kind": "bad_json", "head": (r.stdout or "")[:500]}
    if isinstance(data, dict) and data.get("error"):
        return {"status": "error", "kind": "api_error", "error": str(data["error"])[:500]}
    groups = data.get("post_groups") or []
    if not groups:
        return {"status": "error", "kind": "no_groups"}
    g = groups[0]
    if g.get("error"):
        return {"status": "error", "kind": "group_error", "error": str(g["error"])[:500]}
    out_path = f"{BASE}/raw_pages_desc/page_desc_{page:02d}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return {"status": "ok", "data": data, "group": g, "path": out_path}

def main():
    prog = json.load(open(PROG, encoding="utf-8"))
    page = prog["pages_done"] + 1
    cursor = prog["last_cursor"]
    while True:
        time.sleep(90)
        res = fetch_page(page, cursor)
        if res["status"] != "ok":
            prog["stopped_reason"] = f"stopped at page {page}: {res.get('kind')} {str(res.get('error') or res.get('stderr') or '')[:200]}"
            json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"STOP page {page}: {res.get('kind')}")
            return
        g = res["group"]
        comments = g.get("comments") or []
        prog.update({
            "pages_done": page,
            "last_cursor": g.get("end_cursor"),
            "last_comment_date": comments[-1]["created_at"] if comments else prog.get("last_comment_date"),
            "total_count": g.get("total_count"),
            "stopped_reason": "in_progress",
        })
        json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"PAGE {page}: {len(comments)} comments, has_next={g.get('has_next_page')}, total={g.get('total_count')}", flush=True)
        if not g.get("has_next_page") or not comments:
            prog["stopped_reason"] = "complete"
            json.dump(prog, open(PROG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"CRAWL COMPLETE at page {page}")
            return
        cursor = g.get("end_cursor")
        page += 1

if __name__ == "__main__":
    main()
