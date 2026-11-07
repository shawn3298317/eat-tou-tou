# Taipei Eats 🍜 台北口袋名單

A single-user Taipei restaurant recommendation platform. Pick a cuisine,
a district and a price, get 3–5 ranked picks — or just search for anything.

Seeded from the viral Threads thread by @harriet0308 (Jul 19, 2026):
「一人交出一間你在台北已經 N 刷、吃了還會一直回訪的餐廳」— 4,303 replies.
159 restaurants extracted across two passes (an initial ~100-comment sample
plus 10 more comment pages), each linked to a verified street address and
coordinates where possible, with thread like-counts kept as the
community-response signal. 9 further names could not be verified to a real
place and were left out (see `data/` working files).

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

The CSV is the primary data store: 159 rows, 26 columns. Columns include
`cuisine_primary` and `cuisine_tags`, `district`, `area`, `mrt_station`,
`price_level` (1–4) with `price_min_ntd` / `price_max_ntd` parsed from the
thread's price hints (new rows use price-band bounds, flagged in
`poi_notes`), `must_try`, `mentions` (thread likes), `popularity_score`
(0–100, normalized), `maps_url`, and `source`. Prices are approximate
per-person bands — verify before going.

Every row also carries a canonical POI reference: `canonical_name`,
`poi_address` (verified street address), `poi_latitude` / `poi_longitude`,
`poi_status` (`matched` 107 / `address_only` 49 / `unmatched` 3),
`poi_key` (normalized name + "|" + normalized address, the dedupe key),
and `poi_notes` (branch notes, e.g. other locations or moves). The
`POST /api/restaurants` endpoint rejects duplicates on same poi_key, name,
or verified address (409). The middle of the thread (~Jul 20–Oct 22,
~3,800 comments) is still unsampled — another expansion pass can grow the
list further. Working files from the enrichment passes live in `data/`
(`poi_links.json`, `poi_links_new_{a,b,c}.json`, `new_candidates.json`).

Add a spot from the in-app form (it appends to the CSV via `POST
/api/restaurants`) or by editing the CSV directly and restarting the backend.
To grow the list from the thread, pull more replies with
`threads-cli fetch-post-comments --post-ids 18113719412301018` and append rows.
