"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  CUISINE_LABELS, PRICE_LABELS, addRestaurant, fetchRecommend,
  fetchSearch, fetchStats, fetchTopCuisines,
} from "../lib/api";
import type { Restaurant, TopCuisine } from "../lib/api";

export default function Home() {
  const [query, setQuery] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [district, setDistrict] = useState("");
  const [price, setPrice] = useState("");
  const [count, setCount] = useState("5");
  const [results, setResults] = useState<Restaurant[]>([]);
  const [topCuisines, setTopCuisines] = useState<TopCuisine[]>([]);
  const [districts, setDistricts] = useState<string[]>([]);
  const [cuisineList, setCuisineList] = useState<string[]>([]);
  const [status, setStatus] = useState("Loading…");
  const [mode, setMode] = useState<"recommend" | "search">("recommend");
  const [addMsg, setAddMsg] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runRecommend = useCallback(async () => {
    setMode("recommend");
    setStatus("Ranking…");
    try {
      const list = await fetchRecommend({
        cuisine: cuisine || undefined,
        district: district || undefined,
        price_level: price ? parseInt(price, 10) : undefined,
        n: parseInt(count, 10),
      });
      setResults(list);
      setStatus(
        `Top ${list.length} for ${[cuisine, district, price ? PRICE_LABELS[parseInt(price, 10)] : ""].filter(Boolean).join(" · ") || "anything"}`
      );
    } catch {
      setStatus("Could not reach the API — is the backend running on :8000?");
      setResults([]);
    }
  }, [cuisine, district, price, count]);

  const runSearch = useCallback(async (q: string) => {
    setMode("search");
    setStatus(`Searching for “${q}”…`);
    try {
      const list = await fetchSearch(q, 10);
      setResults(list);
      setStatus(`${list.length} match${list.length === 1 ? "" : "es"} for “${q}”`);
    } catch {
      setStatus("Could not reach the API — is the backend running on :8000?");
      setResults([]);
    }
  }, []);

  // Debounced search as the user types; empty query falls back to recommend.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      if (query.trim()) runSearch(query.trim());
      else runRecommend();
    }, 300);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [query, runSearch, runRecommend]);

  // One-time load: top cuisines by community response + filter options.
  useEffect(() => {
    fetchTopCuisines(8).then(setTopCuisines).catch(() => {});
    fetchStats().then((s) => {
      setDistricts(Object.keys(s.by_district).sort());
      setCuisineList(Object.keys(s.by_cuisine).sort());
    }).catch(() => {});
  }, []);

  function onAdd(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const name = String(f.get("name") || "").trim();
    const tags = String(f.get("cuisine") || "").split(",").map((s) => s.trim()).filter(Boolean);
    const d = String(f.get("district") || "").trim();
    const p = parseInt(String(f.get("price") || "2"), 10);
    if (!name || !tags.length || !d) { setAddMsg("Name, cuisine and district are required."); return; }
    addRestaurant({
      name, cuisine_tags: tags, district: d, price_level: p,
      name_en: String(f.get("name_en") || ""),
      area: String(f.get("area") || ""),
      mrt_station: String(f.get("mrt") || ""),
      must_try: String(f.get("must_try") || ""),
    })
      .then((r) => { setAddMsg(`Saved ✓ (${r.id}) — it is now in data/restaurants.csv.`); e.currentTarget.reset(); runRecommend(); })
      .catch(() => setAddMsg("Save failed — is the backend running?"));
  }

  return (
    <>
      <header>
        <h1>Taipei Eats 🍜 台北口袋名單</h1>
        <p>Seeded from the viral Threads thread (4,303 replies). Search anything, or filter by cuisine, district and price.</p>
      </header>
      <main>
        <section className="panel">
          <input
            className="search" type="text" placeholder="Search — try 拉麵, 牡蠣, 中山, hotpot…"
            value={query} onChange={(e) => setQuery(e.target.value)}
          />
        </section>

        <section className="panel">
          <p className="label">Top cuisines by community response 💬</p>
          <div className="chips">
            {topCuisines.map((t) => (
              <button key={t.cuisine} type="button"
                className={"chip" + (cuisine === t.cuisine ? " on" : "")}
                onClick={() => setCuisine(cuisine === t.cuisine ? "" : t.cuisine)}
                title={`${t.restaurants} spots · ${t.mentions} thread mentions`}>
                {CUISINE_LABELS[t.cuisine] || t.cuisine} <small>{t.mentions} 💬</small>
              </button>
            ))}
          </div>
          <p className="label" style={{ marginTop: 14 }}>Cuisine 類型</p>
          <div className="chips">
            {cuisineList.map((c) => (
              <button key={c} type="button"
                className={"chip" + (cuisine === c ? " on" : "")}
                onClick={() => setCuisine(cuisine === c ? "" : c)}>
                {CUISINE_LABELS[c] || c}
              </button>
            ))}
          </div>
          <p className="label" style={{ marginTop: 14 }}>District 地區 · Price 價位</p>
          <div className="row">
            <select value={district} onChange={(e) => setDistrict(e.target.value)}>
              <option value="">Any district 不限</option>
              {districts.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            <select value={price} onChange={(e) => setPrice(e.target.value)}>
              <option value="">Any price 不限</option>
              {[1, 2, 3, 4].map((p) => <option key={p} value={p}>{PRICE_LABELS[p]}</option>)}
            </select>
            <select value={count} onChange={(e) => setCount(e.target.value)}>
              <option value="3">Top 3</option>
              <option value="5">Top 5</option>
            </select>
            <button className="primary" type="button" onClick={() => { setQuery(""); runRecommend(); }}>Recommend 推薦</button>
          </div>
        </section>

        <div id="status">{status}</div>
        <div>
          {results.length === 0
            ? <p className="empty">No matches — loosen a filter and try again.</p>
            : results.map((r, i) => (
              <article className="card" key={r.id}>
                {r.score != null && (
                  <span className="score"><b>{r.score}</b>score / 100</span>
                )}
                <h3>{mode === "recommend" ? `${i + 1}. ` : ""}{r.name} <span className="en">{r.name_en || ""}</span></h3>
                <div className="meta">📍 {r.district} · {r.area || ""}{r.mrt_station ? ` · 🚇 ${r.mrt_station}` : ""}</div>
                <div className="meta">💰 {PRICE_LABELS[r.price_level] || ""} · NT${r.price_min_ntd}–{r.price_max_ntd}{" "}
                  {r.maps_url && <a href={r.maps_url} target="_blank" rel="noreferrer">Maps ↗</a>}
                </div>
                {r.must_try && <p className="must">必點 <b>{r.must_try}</b></p>}
                <div className="tags">
                  {r.cuisine_tags.map((c) => <span className="tag" key={c}>{CUISINE_LABELS[c] || c}</span>)}
                  <span className="tag">💬 {r.mentions} mentions</span>
                </div>
                {r.score_parts && (
                  <div className="why">
                    Why: cuisine {r.score_parts.cuisine ?? 0} · district {r.score_parts.district ?? 0} · price {r.score_parts.price ?? 0} · popularity {r.score_parts.popularity ?? 0}
                  </div>
                )}
              </article>
            ))}
        </div>

        <section className="panel">
          <details>
            <summary>Add a restaurant 加入一間店</summary>
            <form className="add" onSubmit={onAdd}>
              <input type="text" name="name" placeholder="Name 店名 *" required />
              <input type="text" name="name_en" placeholder="English name (optional)" />
              <div className="row">
                <input type="text" name="cuisine" placeholder="Cuisine tags, comma-separated * e.g. ramen,japanese" required style={{ flex: 1 }} />
                <input type="text" name="district" placeholder="District * e.g. 中山區" required />
                <select name="price">
                  <option value="1">$</option>
                  <option value="2" selected>$$</option>
                  <option value="3">$$$</option>
                  <option value="4">$$$$</option>
                </select>
              </div>
              <div className="row">
                <input type="text" name="area" placeholder="Area / street e.g. 赤峰街" style={{ flex: 1 }} />
                <input type="text" name="mrt" placeholder="MRT e.g. 中山" />
              </div>
              <input type="text" name="must_try" placeholder="Must-try 必點 e.g. 牡蠣拉麵" />
              <button className="primary" type="submit">Save 儲存</button>
              <span>{addMsg}</span>
            </form>
          </details>
        </section>
      </main>
    </>
  );
}
