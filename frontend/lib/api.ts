const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Restaurant = {
  id: string;
  name: string;
  name_en?: string;
  cuisine_primary: string;
  cuisine_tags: string[];
  district: string;
  area?: string;
  mrt_station?: string;
  price_level: number;
  price_label: string;
  price_min_ntd: number;
  price_max_ntd: number;
  must_try?: string;
  mentions: number;
  popularity_score: number;
  maps_url?: string;
  score?: number;
  score_parts?: Record<string, number>;
  search_rank?: number | null;
  match?: string;
};

export type TopCuisine = {
  cuisine: string;
  restaurants: number;
  mentions: number;
};

export const CUISINE_LABELS: Record<string, string> = {
  hotpot: "火鍋", ramen: "拉麵", taiwanese: "台菜", japanese: "日式",
  italian: "義式", korean: "韓式", cantonese: "粵式", shanghainese: "滬菜",
  sichuan: "川湘", noodles: "麵食", dessert: "甜點", vegan: "素食",
  western: "西式", bbq: "燒烤", burgers: "漢堡", curry: "咖哩",
  seafood: "海鮮", "street-snacks": "小吃", jiangzhe: "江浙", shaanxi: "陝西",
};

export const PRICE_LABELS: Record<number, string> = {
  1: "$ < NT$300",
  2: "$$ NT$300–700",
  3: "$$$ NT$700–1,500",
  4: "$$$$ NT$1,500+",
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

export function fetchRecommend(params: {
  cuisine?: string; district?: string; price_level?: number; n?: number;
}): Promise<Restaurant[]> {
  const q = new URLSearchParams();
  if (params.cuisine) q.set("cuisine", params.cuisine);
  if (params.district) q.set("district", params.district);
  if (params.price_level) q.set("price_level", String(params.price_level));
  q.set("n", String(params.n ?? 5));
  return get(`/api/recommend?${q}`);
}

export function fetchSearch(q: string, n = 10): Promise<Restaurant[]> {
  return get(`/api/search?q=${encodeURIComponent(q)}&n=${n}`);
}

export function fetchTopCuisines(limit = 8): Promise<TopCuisine[]> {
  return get(`/api/cuisines/top?limit=${limit}`);
}

export function fetchStats(): Promise<{
  total: number; by_cuisine: Record<string, number>;
  by_district: Record<string, number>; by_price: Record<string, number>;
}> {
  return get("/api/stats");
}

export async function addRestaurant(body: {
  name: string; cuisine_tags: string[]; district: string; price_level: number;
  name_en?: string; area?: string; mrt_station?: string; must_try?: string;
}): Promise<{ ok: boolean; id: string }> {
  const res = await fetch(`${API}/api/restaurants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`add failed: ${res.status}`);
  return res.json();
}
