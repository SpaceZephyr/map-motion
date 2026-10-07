"""高德 Web 服务 API 小客户端：地名→坐标、驾车/步行/骑行路线、行政区边界、POI。坐标一律 GCJ-02 [lng, lat]。

key：环境变量 AMAP_KEY，或 ~/.config/map-motion/amap_key（一行）。
响应缓存在 ~/.cache/map-motion/api/，同一请求不重复打（免费 key 有 QPS 和日配额）。

命令行自查：
  uv run --with certifi python amap.py geo 深圳湾公园
  uv run --with certifi python amap.py route 深圳 广州 --mode driving
  uv run --with certifi python amap.py district 广东省
"""
import hashlib, json, math, os, ssl, sys, time, urllib.parse, urllib.request
from pathlib import Path

CACHE = Path.home() / ".cache/map-motion/api"


def key():
    f = Path.home() / ".config/map-motion/amap_key"
    k = os.environ.get("AMAP_KEY") or (f.read_text().strip() if f.exists() else None)
    if not k: raise SystemExit("没有高德 key：export AMAP_KEY=… 或写进 ~/.config/map-motion/amap_key（高德开放平台 → 应用管理 → Web服务 类型的 key）")
    return k


def _ctx():
    try:
        import certifi; return ssl.create_default_context(cafile=certifi.where())   # macOS 自带 Python 常缺根证书
    except ImportError:
        return ssl.create_default_context()


def get(path, **q):
    q = {k: v for k, v in q.items() if v is not None}
    h = hashlib.md5((path + json.dumps(q, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()
    f = CACHE / f"{h}.json"
    if f.exists(): return json.loads(f.read_text())
    url = f"https://restapi.amap.com{path}?" + urllib.parse.urlencode({**q, "key": key()})
    for attempt in range(6):                                    # 免费 key 约 3 次/秒：间隔＋被限流退避
        time.sleep(0.35 * (attempt + 1))
        d = json.load(urllib.request.urlopen(url, timeout=30, context=_ctx()))
        ok = d.get("status") == "1" or d.get("errcode") == 0
        if ok:
            CACHE.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(d, ensure_ascii=False)); return d
        if str(d.get("infocode")) not in ("10021", "10019", "10020"): break
    raise SystemExit(f"高德 {path} 失败：{d.get('info') or d.get('errmsg')}（{d.get('infocode') or d.get('errcode')}）参数 {q}")


def ll(s): return [float(v) for v in s.split(",")]


def wgs2gcj(lng, lat):
    """WGS-84（GPS、照片 EXIF、GPX）→ GCJ-02（高德）。境外坐标原样返回。"""
    if not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271): return [lng, lat]
    a, ee = 6378245.0, 0.00669342162296594323
    x, y = lng - 105.0, lat - 35.0
    dlat = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x)) + (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3 \
        + (20 * math.sin(y * math.pi) + 40 * math.sin(y / 3 * math.pi)) * 2 / 3 + (160 * math.sin(y / 12 * math.pi) + 320 * math.sin(y * math.pi / 30)) * 2 / 3
    dlng = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x)) + (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3 \
        + (20 * math.sin(x * math.pi) + 40 * math.sin(x / 3 * math.pi)) * 2 / 3 + (150 * math.sin(x / 12 * math.pi) + 300 * math.sin(x / 30 * math.pi)) * 2 / 3
    rad = lat / 180 * math.pi; magic = 1 - ee * math.sin(rad) ** 2; sm = math.sqrt(magic)
    dlat = dlat * 180 / ((a * (1 - ee)) / (magic * sm) * math.pi); dlng = dlng * 180 / (a / sm * math.cos(rad) * math.pi)
    return [round(lng + dlng, 6), round(lat + dlat, 6)]


def geocode(name, city=None):
    """地名/地址 → {lnglat, name, level}。先地理编码；POI 名（景点、大厦）编码不准时退到关键字搜索。"""
    if isinstance(name, (list, tuple)): return {"lnglat": [float(name[0]), float(name[1])], "name": "", "level": "坐标"}
    d = get("/v3/geocode/geo", address=name, city=city)
    g = d.get("geocodes") or []
    # 先信地理编码：行政区名（香格里拉、大理）编码最准；只有编码落到兴趣点/道路级或没结果时才退到关键字搜索
    # （反过来先搜 POI 会把「香格里拉」搜成某家香格里拉酒店）
    poi_like = not g or g[0].get("level") in ("兴趣点", "道路", "道路交叉路口", "门牌号", "未知", "村庄", "热点商圈", "公交站台、地铁站", "公交地铁站点", "住宅区", "商务住宅")
    if poi_like:
        p = get("/v3/place/text", keywords=name, city=city, offset=1, page=1).get("pois") or []
        if p and p[0].get("location"): return {"lnglat": ll(p[0]["location"]), "name": p[0]["name"], "level": "POI"}
    if g: return {"lnglat": ll(g[0]["location"]), "name": g[0]["formatted_address"], "level": g[0].get("level")}
    raise SystemExit(f"高德找不到地点：{name}（换个更具体的叫法，或直接写 [lng, lat]）")


def _dp(pts, tol):
    if len(pts) < 3: return pts
    keep = [False] * len(pts); keep[0] = keep[-1] = True; st = [(0, len(pts) - 1)]
    while st:
        a, b = st.pop(); (x1, y1), (x2, y2) = pts[a], pts[b]; dx, dy = x2 - x1, y2 - y1; L = math.hypot(dx, dy)
        i, dm = 0, -1.0
        for k in range(a + 1, b):
            px, py = pts[k]
            d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / L if L > 1e-12 else math.hypot(px - x1, py - y1)
            if d > dm: i, dm = k, d
        if dm > tol: keep[i] = True; st += [(a, i), (i, b)]
    return [p for p, k in zip(pts, keep) if k]


def simplify(pts, tol=None):
    """按路线跨度自适应抽稀：跨度越大容差越大，长途路线几千点 → 几百点。"""
    if tol is None:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]; span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        tol = span / 2500
    return [[round(x, 6), round(y, 6)] for x, y in _dp(pts, tol)]


def route(o, d, mode="driving", waypoints=None):
    """o/d 为 [lng, lat]。返回 {line, km, hours}。mode：driving | walking | bicycling"""
    f = lambda p: f"{p[0]:.6f},{p[1]:.6f}"
    if mode == "driving":
        r = get("/v3/direction/driving", origin=f(o), destination=f(d), strategy="0",
                waypoints=";".join(f(w) for w in waypoints) if waypoints else None)["route"]["paths"][0]
        steps = r["steps"]
    elif mode == "walking":
        r = get("/v3/direction/walking", origin=f(o), destination=f(d))["route"]["paths"][0]; steps = r["steps"]
    elif mode == "bicycling":
        r = get("/v4/direction/bicycling", origin=f(o), destination=f(d))["data"]["paths"][0]; steps = r["steps"]
    else:
        raise SystemExit(f"不认识的路线方式 {mode}（driving / walking / bicycling；飞线用 arc）")
    line = [ll(p) for s in steps for p in s["polyline"].split(";") if p]
    return {"line": simplify(line), "km": round(int(r["distance"]) / 1000, 2), "hours": round(int(r["duration"]) / 3600, 2)}


def district(name):
    """行政区名 → {name, adcode, center, rings}（rings 为外轮廓列表，已抽稀）"""
    d = get("/v3/config/district", keywords=name, subdistrict=0, extensions="all")["districts"]
    if not d: raise SystemExit(f"高德没有这个行政区：{name}")
    x = d[0]; rings = [[ll(p) for p in seg.split(";")] for seg in (x.get("polyline") or "").split("|") if seg]
    if not rings: raise SystemExit(f"{name} 没有边界数据")
    span = max(max(p[0] for r in rings for p in r) - min(p[0] for r in rings for p in r), 0.01)
    rings = [simplify(r, span / 1500) for r in rings]
    return {"name": x["name"], "adcode": x["adcode"], "center": ll(x["center"]), "rings": [r for r in rings if len(r) >= 4]}


if __name__ == "__main__":
    cmd, *args = sys.argv[1:] or ["help"]
    if cmd == "geo": print(geocode(args[0]))
    elif cmd == "route":
        mode = args[args.index("--mode") + 1] if "--mode" in args else "driving"
        r = route(geocode(args[0])["lnglat"], geocode(args[1])["lnglat"], mode); print(f"{r['km']} km, {r['hours']} h, {len(r['line'])} 点")
    elif cmd == "district": r = district(args[0]); print(r["name"], r["adcode"], r["center"], [len(x) for x in r["rings"]])
    else: print(__doc__)
