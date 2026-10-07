"""地块轮廓（公园、景区、校园、小区…）与轨迹文件 → GCJ-02 坐标。

高德 Web 服务不给面状地物的边界，这里从 OpenStreetMap（Overpass）按名字在地点附近查；
轨迹文件支持 GPX（trkpt/rtept）、GeoJSON（LineString/MultiLineString/Polygon）。
OSM、GPX、GeoJSON 都是 WGS-84，统一转成 GCJ-02 才能和高德底图对齐。
结果缓存在 ~/.cache/map-motion/osm/。

命令行自查：uv run --with certifi python osm.py 桂林公园 121.4179 31.1653
"""
import hashlib, json, math, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import amap

CACHE = Path.home() / ".cache/map-motion/osm"
MIRRORS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
AREA_TAGS = ("leisure", "landuse", "tourism", "amenity", "natural", "historic", "boundary", "place", "building", "water")


def overpass(q):
    f = CACHE / (hashlib.md5(q.encode()).hexdigest() + ".json")
    if f.exists(): return json.loads(f.read_text())
    err = None
    for u in MIRRORS:                                            # 主站常 504，轮流试镜像
        try:
            req = urllib.request.Request(u, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": "map-motion/1.0 (video tool)"})
            d = json.load(urllib.request.urlopen(req, timeout=90, context=amap._ctx()))
            CACHE.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(d, ensure_ascii=False)); return d
        except Exception as e:
            err = e; time.sleep(1)
    raise SystemExit(f"OSM 查询失败（{err}）。可改用 geojson 文件或直接写 rings。")


def _join(segs):
    """把关系里的若干 outer 段首尾拼成闭环"""
    segs = [s[:] for s in segs if len(s) > 1]; rings = []
    while segs:
        ring = segs.pop(0)
        while ring[0] != ring[-1]:
            for i, s in enumerate(segs):
                if s[0] == ring[-1]: ring += s[1:]; segs.pop(i); break
                if s[-1] == ring[-1]: ring += s[::-1][1:]; segs.pop(i); break
            else: break
        rings.append(ring)
    return rings


def _inside(p, ring):
    x, y, c = p[0], p[1], False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i], ring[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-15) + x1: c = not c
    return c


def area(name, near, radius=0.03):
    """near 为 GCJ [lng, lat]（高德解析的位置）。返回 {rings(GCJ), tags, source}；选包含该点的、否则离得最近的那块。"""
    lng, lat = near; b = f"{lat - radius},{lng - radius},{lat + radius},{lng + radius}"
    nm = name.replace('"', "")
    d = overpass(f'[out:json][timeout:60];(way["name"~"{nm}"]({b});relation["name"~"{nm}"]({b}););out geom;')
    cands = []
    for e in d.get("elements", []):
        tags = e.get("tags", {})
        if not any(k in tags for k in AREA_TAGS) or tags.get("railway") or tags.get("public_transport"): continue   # 同名地铁站、站台不要
        if e["type"] == "way": rings = [[[p["lon"], p["lat"]] for p in e.get("geometry", [])]]
        else: rings = _join([[[p["lon"], p["lat"]] for p in m.get("geometry", [])] for m in e.get("members", []) if m.get("role") == "outer"])
        rings = [[amap.wgs2gcj(*p) for p in r] for r in rings if len(r) >= 4]
        if not rings: continue
        cx = sum(p[0] for p in rings[0]) / len(rings[0]); cy = sum(p[1] for p in rings[0]) / len(rings[0])
        score = (0 if any(_inside(near, r) for r in rings) else 1, math.hypot(cx - lng, cy - lat))
        cands.append((score, {"rings": rings, "tags": tags, "source": f"OSM {e['type']}/{e['id']}"}))
    if not cands: raise SystemExit(f"OSM 在 {near} 附近没有叫「{name}」的地块。可换名字（OSM 常用全称）、用 geojson 文件，或直接写 rings。")
    return min(cands, key=lambda c: c[0])[1]


def track(path, wgs84=True):
    """GPX / GeoJSON 轨迹 → GCJ 点列（多段首尾相接）"""
    p = Path(path); pts = []
    if p.suffix.lower() == ".gpx":
        root = ET.parse(p).getroot()
        for el in root.iter():
            if el.tag.split("}")[-1] in ("trkpt", "rtept"): pts.append([float(el.get("lon")), float(el.get("lat"))])
    else:
        g = json.loads(p.read_text()); feats = g["features"] if g.get("type") == "FeatureCollection" else [g]
        for f in feats:
            geo = f.get("geometry", f); t, c = geo["type"], geo["coordinates"]
            if t == "LineString": pts += c
            elif t in ("MultiLineString", "Polygon"): pts += [q for line in c for q in line]
            elif t == "MultiPolygon": pts += [q for poly in c for q in poly[0]]
    if len(pts) < 2: raise SystemExit(f"轨迹文件里没有点：{path}")
    pts = [[q[0], q[1]] for q in pts]
    return [amap.wgs2gcj(*q) for q in pts] if wgs84 else pts


if __name__ == "__main__":
    n, x, y = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); r = area(n, [x, y])
    print(r["source"], r["tags"].get("name"), [len(q) for q in r["rings"]], r["rings"][0][:2])
