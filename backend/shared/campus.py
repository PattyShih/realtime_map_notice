"""輔仁大學校園地標判別：把 GPS 座標對應到「哪一棟大樓／哪個區域」。

設計考量：
- 只對落在輔大範圍內（bounding box）的座標判別；校外事件回 None，不做逆向
  地理編碼（Nominatim 對校園建物的覆蓋不齊，且多一次外部依賴）
- POI 採「最近且在半徑內者勝」：校舍密集處半徑給小（60–80m）避免誤判到隔壁棟，
  大區域（操場、停車場）給大半徑
- 座標為近似值（校園平面圖對位，誤差約 ±30–60m），可在這份清單直接微調；
  新增大樓只要加一筆 dict，不需改程式

用法：
    from backend.shared.campus import resolve_campus_location
    label = resolve_campus_location(lat, lng)  # "文開樓（外語學院）" 或 None
"""
import math

# 輔大校園 bounding box（含校外宿舍與醫院周邊）；座標在此範圍外不判別
CAMPUS_BOUNDS = {
    "lat_min": 25.0290,
    "lat_max": 25.0398,
    "lng_min": 121.4220,
    "lng_max": 121.4395,
}

# 校園地標清單：(名稱, 緯度, 經度, 判別半徑公尺)
CAMPUS_POIS = [
    # 圖書館與教學大樓
    ("輔大總圖書館", 25.03720, 121.43250, 80),
    ("文開樓（外語學院）", 25.03590, 121.43130, 70),
    ("文友樓（文學院）", 25.03530, 121.43170, 70),
    ("文德樓（教育學院）", 25.03580, 121.43220, 60),
    ("濟時樓（法律學院）", 25.03420, 121.43160, 70),
    ("羅耀拉大樓（社科院）", 25.03460, 121.43120, 70),
    ("理圖思樓（理工學院）", 25.03490, 121.43050, 90),
    ("聖言樓（管理學院）", 25.03370, 121.43100, 80),
    ("織品學院（織品大樓）", 25.03520, 121.42980, 70),
    ("民生學院", 25.03570, 121.43280, 60),
    ("醫學院（輔大校區）", 25.03330, 121.43230, 80),
    ("立德教學大樓", 25.03390, 121.43220, 60),
    # 體育與活動場域
    ("中美堂", 25.03600, 121.43300, 80),
    ("風雨籃球場", 25.03470, 121.43410, 70),
    ("田徑場（運動場）", 25.03440, 121.43520, 110),
    ("體育館", 25.03410, 121.43460, 70),
    # 生活場域
    ("學生活動中心／學餐", 25.03650, 121.43350, 90),
    ("宜真學苑（女宿）", 25.03680, 121.43180, 70),
    ("仁園學舍（男宿）", 25.03610, 121.43440, 80),
    ("文舍學苑", 25.03760, 121.43380, 70),
    # 校園周邊地標
    ("捷運輔大站", 25.03330, 121.43400, 130),
    ("輔大醫院", 25.03120, 121.42470, 160),
]


def _distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine 直線距離（公尺），小範圍足夠精確。"""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def resolve_campus_location(latitude: float, longitude: float) -> str | None:
    """座標在輔大範圍內時，回傳最近的地標名稱；校外或無匹配回 None。"""
    b = CAMPUS_BOUNDS
    if not (b["lat_min"] <= latitude <= b["lat_max"] and b["lng_min"] <= longitude <= b["lng_max"]):
        return None

    best: tuple[str, float] | None = None
    for name, poi_lat, poi_lng, radius in CAMPUS_POIS:
        dist = _distance_meters(latitude, longitude, poi_lat, poi_lng)
        if dist <= radius and (best is None or dist < best[1]):
            best = (name, dist)
    return best[0] if best else None
