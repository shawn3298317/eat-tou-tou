"""Taipei Eats API — FastAPI backend.

Primary data store: ../data/restaurants.csv (edit the CSV, restart, done).
Retrieval is off-the-shelf only, no trained models:
  - SQLite FTS5 (stdlib sqlite3) for full-text search with BM25 ranking.
  - In-memory weighted scoring for recommendations.

Run:
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  uvicorn main:app --reload --port 8000
"""
import csv
import math
import os
import re
import sqlite3
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE, "..", "data", "restaurants.csv")

RELATED = {
    "ramen": {"japanese", "noodles"},
    "noodles": {"ramen", "taiwanese", "shaanxi"},
    "japanese": {"ramen", "curry"},
    "hotpot": {"sichuan"},
    "sichuan": {"hotpot"},
    "taiwanese": {"noodles", "street-snacks", "seafood"},
    "dessert": {"japanese", "italian"},
    "italian": {"dessert", "western"},
    "western": {"italian", "burgers"},
    "burgers": {"western"},
    "bbq": {"korean"},
    "korean": {"bbq"},
    "cantonese": {"shanghainese"},
    "shanghainese": {"cantonese", "jiangzhe"},
    "jiangzhe": {"shanghainese"},
    "seafood": {"taiwanese"},
    "curry": {"japanese"},
    "vegan": {"western"},
}

app = FastAPI(title="Taipei Eats API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_lock = threading.Lock()
_restaurants: list[dict] = []
_fts: Optional[sqlite3.Connection] = None


def _parse_row(row: dict) -> dict:
    r = dict(row)
    r["cuisine_tags"] = [t for t in row.get("cuisine_tags", "").split(";") if t]
    for k in ("price_level", "price_min_ntd", "price_max_ntd", "mentions", "popularity_score"):
        try:
            r[k] = int(float(row.get(k) or 0))
        except ValueError:
            r[k] = 0
    for k in ("poi_latitude", "poi_longitude"):
        try:
            r[k] = float(row.get(k)) if row.get(k) else None
        except ValueError:
            r[k] = None
    return r


def load_data() -> None:
    """Load the CSV into memory and (re)build the FTS5 search index."""
    global _restaurants, _fts
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        _restaurants = [_parse_row(r) for r in csv.DictReader(f)]
    if _fts is not None:
        _fts.close()
    _fts = sqlite3.connect(":memory:", check_same_thread=False)
    _fts.execute(
        "CREATE VIRTUAL TABLE fts USING fts5("
        "name, name_en, cuisine_tags, district, area, must_try, poi_address, "
        "tokenize='unicode61')"
    )
    for i, r in enumerate(_restaurants):
        _fts.execute(
            "INSERT INTO fts(rowid, name, name_en, cuisine_tags, district, area, must_try, poi_address)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (i, r["name"], r.get("name_en", ""), " ".join(r["cuisine_tags"]),
             r.get("district", ""), r.get("area", ""), r.get("must_try", ""),
             r.get("poi_address", "") or ""),
        )
    _fts.commit()


def score(r: dict, cuisine: Optional[str] = None,
          district: Optional[str] = None,
          price_level: Optional[int] = None) -> tuple[float, dict]:
    parts, s = {}, 0.0
    if cuisine:
        tags = set(r["cuisine_tags"])
        parts["cuisine"] = 40 if cuisine in tags else (
            15 if tags & RELATED.get(cuisine, set()) else 0)
        s += parts["cuisine"]
    if district:
        parts["district"] = 25 if r.get("district") == district else 0
        s += parts["district"]
    if price_level is not None:
        d = abs(r.get("price_level", 2) - price_level)
        parts["price"] = 20 if d == 0 else (10 if d == 1 else 0)
        s += parts["price"]
    pop = min(15.0, 5.0 * math.log1p(r.get("mentions", 0)))
    parts["popularity"] = round(pop, 1)
    s += pop
    return round(s, 1), parts


def recommend(cuisine=None, district=None, price_level=None, n=5):
    out = []
    for r in _restaurants:
        s, parts = score(r, cuisine, district, price_level)
        out.append({**r, "score": s, "score_parts": parts})
    if cuisine:
        out = [x for x in out if x["score_parts"].get("cuisine", 0) > 0]
    if district:
        out = [x for x in out if x["score_parts"].get("district", 0) > 0]
    # Exact cuisine matches always outrank related-cuisine ones.
    out.sort(key=lambda x: (-x["score_parts"].get("cuisine", 0),
                            -x["score"], -x.get("mentions", 0)))
    return out[:n]


@app.on_event("startup")
def _startup():
    load_data()


@app.get("/api/health")
def health():
    return {"ok": True, "restaurants": len(_restaurants)}


@app.get("/api/restaurants")
def list_restaurants(
    cuisine: Optional[str] = None,
    district: Optional[str] = None,
    price_level: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    out = _restaurants
    if cuisine:
        out = [r for r in out if cuisine in r["cuisine_tags"]]
    if district:
        out = [r for r in out if r.get("district") == district]
    if price_level is not None:
        out = [r for r in out if r.get("price_level") == price_level]
    return {"total": len(out), "results": out[offset:offset + limit]}


@app.get("/api/restaurants/{rid}")
def get_restaurant(rid: str):
    for r in _restaurants:
        if r["id"] == rid:
            return r
    raise HTTPException(404, "restaurant not found")


@app.get("/api/recommend")
def get_recommend(
    cuisine: Optional[str] = None,
    district: Optional[str] = None,
    price_level: Optional[int] = None,
    n: int = Query(5, ge=1, le=20),
):
    return recommend(cuisine, district, price_level, n)


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), n: int = Query(10, ge=1, le=50)):
    """Full-text search, two off-the-shelf layers, no trained models:
    1. SQLite FTS5 with BM25 for token queries (latin names, tags, MRT).
    2. Substring scan over the in-memory rows for CJK, which FTS5's
       unicode61 tokenizer does not split into searchable tokens.
    FTS matches come first (BM25 ranked), substring matches fill the rest.
    """
    ql = q.strip().lower()
    seen: set[int] = set()
    out: list[dict] = []
    try:
        cur = _fts.execute(
            "SELECT rowid, bm25(fts) AS rank FROM fts WHERE fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (q, n),
        )
        for rowid, rank in cur.fetchall():
            r = dict(_restaurants[rowid])
            r["search_rank"] = round(rank, 3)
            r["match"] = "fts"
            out.append(r)
            seen.add(rowid)
    except sqlite3.OperationalError:
        pass  # query syntax FTS5 cannot parse; substring scan still applies
    if len(out) < n:
        for i, r in enumerate(_restaurants):
            if i in seen:
                continue
            hay = " ".join([r["name"], r.get("name_en", ""),
                            " ".join(r["cuisine_tags"]), r.get("district", ""),
                            r.get("area", ""), r.get("must_try", "")]).lower()
            if ql in hay:
                r2 = dict(r)
                r2["search_rank"] = None
                r2["match"] = "substring"
                out.append(r2)
                seen.add(i)
                if len(out) >= n:
                    break
    return out[:n]


@app.get("/api/cuisines/top")
def top_cuisines(limit: int = Query(8, ge=1, le=20)):
    """Cuisine types ranked by community response (thread mentions)."""
    agg: dict[str, dict] = {}
    for r in _restaurants:
        for tag in r["cuisine_tags"]:
            a = agg.setdefault(tag, {"cuisine": tag, "restaurants": 0, "mentions": 0})
            a["restaurants"] += 1
            a["mentions"] += r.get("mentions", 0)
    ranked = sorted(agg.values(), key=lambda a: (-a["mentions"], -a["restaurants"]))
    return ranked[:limit]


@app.get("/api/stats")
def stats():
    by_cuisine, by_district, by_price = {}, {}, {}
    for r in _restaurants:
        for c in r["cuisine_tags"]:
            by_cuisine[c] = by_cuisine.get(c, 0) + 1
        by_district[r.get("district")] = by_district.get(r.get("district"), 0) + 1
        by_price[str(r.get("price_level"))] = by_price.get(str(r.get("price_level")), 0) + 1
    return {"total": len(_restaurants), "by_cuisine": by_cuisine,
            "by_district": by_district, "by_price": by_price,
            "by_poi_status": {s: sum(1 for r in _restaurants
                                     if r.get("poi_status") == s)
                              for s in ("matched", "address_only", "unmatched")}}


class RestaurantIn(BaseModel):
    name: str
    cuisine_tags: list[str] = Field(..., min_length=1)
    district: str
    price_level: int = Field(..., ge=1, le=4)
    name_en: str = ""
    area: str = ""
    mrt_station: str = ""
    price_min_ntd: int = 0
    price_max_ntd: int = 0
    must_try: str = ""
    mentions: int = 0
    canonical_name: str = ""
    poi_address: str = ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


@app.post("/api/restaurants", status_code=201)
def add_restaurant(body: RestaurantIn):
    """Append a row to the CSV (the primary store) and rebuild the index.

    Dedupe runs on the canonical POI key before anything is written:
    same canonical name + verified address, same name, or same verified
    address as an existing row is rejected with 409. A row added without
    a verified address lands as poi_status=unmatched so it can be linked
    later instead of silently duplicating a place.
    """
    with _lock:
        rid = body.name.lower().replace(" ", "-")
        if any(r["id"] == rid for r in _restaurants):
            raise HTTPException(409, "a restaurant with that id already exists")
        canon = body.canonical_name or body.name
        key = (_norm(canon) + "|" + _norm(body.poi_address)) if body.poi_address else ""
        for r in _restaurants:
            if key and r.get("poi_key") == key:
                raise HTTPException(409, f"duplicate of {r['id']}: same canonical name + address")
            if _norm(r["name"]) == _norm(body.name) or _norm(r.get("canonical_name", "")) == _norm(canon):
                raise HTTPException(409, f"duplicate of {r['id']}: same name")
            if body.poi_address and _norm(r.get("poi_address", "")) == _norm(body.poi_address):
                raise HTTPException(409, f"duplicate of {r['id']}: same verified address")
        row = {
            "id": rid, "name": body.name, "name_en": body.name_en,
            "cuisine_primary": body.cuisine_tags[0],
            "cuisine_tags": ";".join(body.cuisine_tags),
            "district": body.district, "area": body.area,
            "mrt_station": body.mrt_station,
            "price_level": body.price_level,
            "price_label": {1: "$", 2: "$$", 3: "$$$", 4: "$$$$"}[body.price_level],
            "price_min_ntd": body.price_min_ntd,
            "price_max_ntd": body.price_max_ntd,
            "must_try": body.must_try, "mentions": body.mentions,
            "popularity_score": 0, "source": "user",
            "maps_url": "",
            "notes": "Added via API.",
            "added_at": "2026-11-07",
            "canonical_name": canon,
            "poi_address": body.poi_address,
            "poi_latitude": "", "poi_longitude": "",
            "poi_status": "address_only" if body.poi_address else "unmatched",
            "poi_key": key,
            "poi_notes": "",
        }
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writerow({k: row.get(k, "") for k in header})
        load_data()
    return {"ok": True, "id": rid}
