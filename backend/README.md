# Taipei Eats — backend (FastAPI)

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## Data

Primary store is `../data/restaurants.csv`. Edit the CSV and restart (or
`POST /api/restaurants` to append a row). The server loads it into memory at
startup and builds an SQLite FTS5 full-text index — off-the-shelf retrieval,
no trained models.

## POI references and dedupe

Each row carries a canonical place reference, resolved by Google search +
geocode against the real venue (see `../data/poi_links.json` for the
evidence trail):

- `canonical_name`, `poi_address` (verified street address),
  `poi_latitude` / `poi_longitude`, `poi_status`
  (`matched` = geocode returned the venue name at that address;
  `address_only` = address confirmed, name not in the geocode result;
  `unmatched` = no verified address found yet).
- `poi_key` = normalized canonical name + "|" + normalized address.
  It is the canonical dedupe key: two rows with the same key are the same
  place (this is what separates 鼎旺一店 from 二店, or 麵屋雞金's branches).
- `poi_notes` records branch notes (other locations, moves, renames).

`POST /api/restaurants` refuses duplicates with 409: same poi_key, same
name, or same verified address as an existing row. A row added without a
verified address lands as `unmatched` so it can be linked later instead of
silently duplicating a place.

One honest limitation: no numeric Google `place_id` values were retrievable
with the tools available here (search returns no place-ID blocks for Taipei
venues, and the HasData connector is not connected). The dedupe key is
verified name + address + coordinates, which resolves the branch problem;
true `place_id`s would need a Places API key or HasData.

## Endpoints

- `GET /api/health`
- `GET /api/restaurants?cuisine=&district=&price_level=&limit=&offset=`
- `GET /api/restaurants/{id}`
- `GET /api/recommend?cuisine=&district=&price_level=&n=5` — weighted score:
  cuisine 40 (15 related) + district 25 + price 20 + popularity up to 15
- `GET /api/search?q=&n=10` — FTS5 full-text search, BM25 ranked
- `GET /api/cuisines/top?limit=8` — cuisine types by community response (thread mentions)
- `GET /api/stats`
- `POST /api/restaurants` — append a row to the CSV
