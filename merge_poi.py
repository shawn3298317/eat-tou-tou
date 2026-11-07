"""Merge POI resolutions into data/restaurants.csv.

Sources:
  - poi_links.json (subagent: 27 rows, searched + geocoded)
  - MY_GEOCODE: 17 rows resolved by the parent's own geocode calls this session
Adds columns: canonical_name, poi_address, poi_latitude, poi_longitude,
poi_status, poi_key, poi_notes. Updates district / area / mrt_station /
maps_url from the verified POI where available.
poi_key = normalized canonical name + '|' + normalized address; it is the
canonical dedupe key (empty for unmatched rows).
"""
import csv
import json
import re
import unicodedata

BASE = "/home/hatch/workspace/taipei-eats"
CSV = f"{BASE}/data/restaurants.csv"
LINKS = f"{BASE}/data/poi_links.json"

# id -> (canonical_name, address, district, lat, lng, mrt, status, notes)
MY_GEOCODE = {
    "dingwang": ("鼎旺麻辣鍋", "台北市大安區大安路一段251號", "大安區", 25.03364, 121.54608,
                 "大安站", "matched", "二店: 大安路一段229號"),
    "menya-kogane": ("麵屋雞金", "台北市中正區新生南路一段6號", "中正區", 25.04402, 121.53262,
                     "忠孝新生站", "matched", "分店: 延吉店 延吉街135-1號; 科技大樓店 和平東路二段255號"),
    "longquan-noodle": ("龍泉市場無名麵攤", "台北市大安區師大路92巷15號", "大安區", 25.02274, 121.5273,
                        "台電大樓站", "address_only", "另有來源稱 117巷4號; 以 92巷15號為準"),
    "kangleyi": ("康樂意小吃店", "台北市中正區汀州路二段46號", "中正區", 25.02524, 121.51786,
                 "古亭站", "matched", ""),
    "qiantangcun": ("錢唐村", "台北市大安區仁愛路四段122巷48號", "大安區", 25.03462, 121.55015,
                    "信義安和站", "matched", ""),
    "sunami": ("Sunami 蔬納米", "台北市大安區市民大道四段10號", "大安區", 25.04468, 121.54434,
               "忠孝復興站", "matched", ""),
    "erya": ("二屋牡蠣拉麵", "台北市大同區赤峰街37巷", "大同區", 25.0546, 121.52025,
             "中山站", "matched", "赤峰街北側屬大同區; 街號未在 geocode 回傳中顯示"),
    "jijiazhuang": ("雞家莊", "台北市中山區長春路55號", "中山區", 25.05502, 121.52615,
                    "松江南京站", "matched", ""),
    "huangji": ("黃記魯肉飯", "台北市中山區中山北路二段183巷28號", "中山區", 25.06369, 121.5241,
                "中山國小站", "matched", ""),
    "shiyi": ("時飴 Approprié", "台北市大同區赤峰街8巷22號", "大同區", 25.05373, 121.51854,
              "中山站", "matched", "分店: 仁愛圓環店 仁愛路四段105巷7號"),
    "yuhongyuan": ("魚紅苑重慶烤魚", "台北市中山區中山北路二段59巷46號", "中山區", 25.05578, 121.52469,
                   "中山站", "matched", ""),
    "batie-laozhai": ("八條老宅麻辣鍋", "台北市中山區林森北路133巷3號", "中山區", 25.05107, 121.52547,
                      "中山站", "matched", ""),
    "paipai": ("PAI PAI CANNOLI", "台北市大同區赤峰街17巷5號", "大同區", 25.05382, 121.51956,
               "中山站", "matched", ""),
    "teafire": ("茶火間 TEA FIRE", "台北市大安區市民大道四段68巷1號", "大安區", 25.04476, 121.54737,
                "忠孝敦化站", "address_only", ""),
    "russia-bbq": ("RUSSIA BBQ 俄羅斯烤肉", "台北市大安區文昌街168號", "大安區", 25.03244, 121.55367,
                   "信義安和站", "address_only", "geocode relevance 偏低 (60); 巷/號待確認"),
    "yushi": ("畬室", "台北市大安區仁愛路四段112巷3弄10號", "大安區", 25.03706, 121.55013,
              "忠孝復興站", "matched", ""),
    "kaifan": ("開飯川食堂", "台北市大安區忠孝東路四段98號", "大安區", 25.04126, 121.54627,
               "忠孝復興站", "matched", "分店: 信義店 忠孝東路五段8號"),
}

NEW_COLS = ["canonical_name", "poi_address", "poi_latitude", "poi_longitude",
            "poi_status", "poi_key", "poi_notes"]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"\s+", "", s).lower()


def street_of(address: str) -> str:
    m = re.sub(r"^(?:台北市|新北市)[^區]+區", "", address or "")
    return m


def main():
    with open(LINKS, encoding="utf-8") as f:
        links = {r["id"]: r for r in json.load(f)}

    resolved = {}
    for rid, (name, addr, dist, lat, lng, mrt, status, notes) in MY_GEOCODE.items():
        resolved[rid] = {"canonical_name": name, "verified_address": addr,
                         "district": dist, "latitude": lat, "longitude": lng,
                         "mrt_station": mrt, "poi_status": status, "branch_notes": notes}
    for rid, r in links.items():
        resolved[rid] = r

    with open(CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else []

    assert len(resolved) == 44, f"expected 44 resolved, got {len(resolved)}"
    missing = [r["id"] for r in rows if r["id"] not in resolved]
    assert not missing, f"unresolved rows: {missing}"

    from urllib.parse import quote
    n_updated_district = 0
    keys_seen = {}
    dup_keys = []
    for row in rows:
        r = resolved[row["id"]]
        status = r["poi_status"]
        row["canonical_name"] = r["canonical_name"] or row["name"]
        row["poi_address"] = r["verified_address"] or ""
        row["poi_latitude"] = str(r["latitude"]) if r.get("latitude") is not None else ""
        row["poi_longitude"] = str(r["longitude"]) if r.get("longitude") is not None else ""
        row["poi_status"] = status
        if status != "unmatched" and r["verified_address"]:
            row["poi_key"] = norm(r["canonical_name"]) + "|" + norm(r["verified_address"])
            if row["poi_key"] in keys_seen:
                dup_keys.append((row["poi_key"], keys_seen[row["poi_key"]], row["id"]))
            keys_seen[row["poi_key"]] = row["id"]
            if r.get("district") and r["district"] != row["district"]:
                n_updated_district += 1
                row["district"] = r["district"]
            row["area"] = street_of(r["verified_address"])
            if r.get("mrt_station"):
                row["mrt_station"] = r["mrt_station"].rstrip("站")
            row["maps_url"] = ("https://www.google.com/maps/search/?api=1&query="
                               + quote(r["verified_address"]))
        else:
            row["poi_key"] = ""
        row["poi_notes"] = r.get("branch_notes", "") or ""

    out_fields = fields + [c for c in NEW_COLS if c not in fields]
    with open(CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        w.writerows(rows)

    from collections import Counter
    print("rows:", len(rows))
    print("poi_status:", dict(Counter(r["poi_status"] for r in rows)))
    print("district corrections:", n_updated_district)
    print("duplicate poi_keys:", dup_keys or "none")
    print("districts now:", dict(Counter(r["district"] for r in rows)))


if __name__ == "__main__":
    main()
