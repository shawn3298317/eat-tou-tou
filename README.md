# Taipei Eats 🍜 台北口袋名單

A single-user Taipei restaurant recommendation platform. Pick a cuisine,
a district and a price, get 3–5 ranked picks — or just search for anything.

Seeded from the viral Threads thread by @harriet0308 (Jul 19, 2026):
「一人交出一間你在台北已經 N 刷、吃了還會一直回訪的餐廳」— 4,303 replies.
789 restaurants extracted from the full thread (every comment page, Jul 19–
Nov 6), each linked to a verified street address and coordinates where
possible, with thread like-counts kept as the community-response signal
(shared list-comment likes are split across the places in that comment).
84 further names could not be verified to a real place and were left out
(see `data/` working files).

## Stack

| Layer | Tech |
|---|---|
| Data (primary store) | `data/restaurants.csv` — 44 rows, 19 columns |
| Backend | FastAPI + SQLite FTS5 (stdlib `sqlite3`), `backend/` |
| Frontend | Next.js App Router (React 19), `frontend/` |

No trained models anywhere. Retrieval is off-the-shelf: FTS5 with BM25 for
full-text search, plus a weighted score for recommendations.

## Quick start

```bash
# Backend (port 8000)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (port 3000) — in a second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. API docs at http://localhost:8000/docs.

## How ranking works

`GET /api/recommend?cuisine=ramen&district=中山區&price_level=1&n=5`

Score out of 100: cuisine match 40 (15 for a related cuisine, e.g. ramen ↔
japanese) + district 25 + price fit 20 + popularity up to 15 (log-scaled
thread mentions). Exact cuisine matches always outrank related ones.

`GET /api/search?q=牡蠣` runs two layers: SQLite FTS5 with BM25 for token
queries, and a substring scan for CJK, which FTS5's unicode61 tokenizer
does not split into searchable tokens.

`GET /api/cuisines/top` ranks cuisine types by total thread mentions —
the "community response" strip on the homepage.

## Data — `data/restaurants.csv`

The CSV is the primary data store: 789 rows, 26 columns. Columns include
`cuisine_primary` and `cuisine_tags`, `district`, `area`, `mrt_station`,
`price_level` (1–4) with `price_min_ntd` / `price_max_ntd` parsed from the
thread's price hints (rows linked in the expansion passes use price-band
bounds, flagged in `poi_notes`), `must_try`, `mentions` (thread likes,
shared list-comment likes split across the places in that comment),
`popularity_score` (0–100, normalized), `maps_url`, and `source`. Prices
are approximate per-person bands — verify before going.

Every row also carries a canonical POI reference: `canonical_name`,
`poi_address` (verified street address), `poi_latitude` / `poi_longitude`,
`poi_status` (`matched` 584 / `address_only` 202 / `unmatched` 3),
`poi_key` (normalized name + "|" + normalized address, the dedupe key,
with parenthetical branch suffixes stripped so same-venue pairs collapse),
and `poi_notes` (branch notes, e.g. other locations or moves). The
`POST /api/restaurants` endpoint rejects duplicates on same poi_key, name,
or verified address (409). The full thread was crawled in five paced
batches (90s between calls, checkpoints after every page); the raw page
JSONs live in `data/raw_pages_desc/` and the candidate + POI-link working
files in `data/` (`new_candidates_desc.json`, `poi_links_desc_{a..l}.json`,
`crawl_progress_desc.json`).

Add a spot from the in-app form (it appends to the CSV via `POST
/api/restaurants`) or by editing the CSV directly and restarting the backend.
To grow the list from the thread, pull more replies with
`threads-cli fetch-post-comments --post-ids 18113719412301018` and append rows.

## Tokyo — `data/tokyo_restaurants.csv`

Same crawl-and-enrich flow, second city. Source is @rita611293's Threads
post (Jun 12, 2026): 「求 東京 讓你們最驚艷最最最最愛的食物！！！！」—
2,932 likes, 311 replies, all crawled Nov 10, 2026 (309 comments fetched,
7 pages, same 90s pacing and per-page checkpoints). 73 candidates
extracted, 71 rows merged (68 matched / 3 address-only / 0 unmatched).

Same 26-column shape as the Taipei CSV, plus `currency` (JPY) and
`price_min_jpy` / `price_max_jpy` instead of the NTD price columns. Price
bands in yen: 1 under ¥1,000, 2 ¥1,000–2,500, 3 ¥2,500–5,000, 4 over
¥5,000. `district` is the Tokyo neighborhood (浅草, 渋谷, 新宿, ...);
`area` is the street part of the address; `mrt_station` is the station
name only. Shared list-comment likes are split across the places in that
comment (the 29-name list comment splits 221 likes to ~8 each); duplicate
mentions fold into their canonical row (yellow蛋包飯 +4 into EDW, 鴨拉麵上野
+0 into 鴨to蔥). Working files live in `data/tokyo/` (raw pages, candidates,
`poi_links_tokyo_{a..f}.json`, `merge_tokyo.py`, `crawl_tokyo.py`).

Two threads' top-liked comments (420 and 382 likes) are photo posts with no
venue name in the text and could not be identified. 川豐 is in Narita, not
Tokyo, and is flagged as a day trip. Prices are approximate per-person JPY
bands — verify before going.
