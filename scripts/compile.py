"""镜头表 spec.json → timeline.json（地名/路线/边界都经高德解析好，相机关键帧与图层时间都算好）。
uv run --with certifi python compile.py spec.json [--out timeline.json]
spec 写法见 references/spec.md。
"""
import argparse, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import amap, osm, elev

ap = argparse.ArgumentParser(); ap.add_argument("spec"); ap.add_argument("--out"); A = ap.parse_args()
sp = Path(A.spec).resolve(); SPEC = json.loads(sp.read_text())
out = Path(A.out).resolve() if A.out else sp.with_name(sp.stem + ".timeline.json")
SIZES = {"portrait": (1080, 1920), "landscape": (1920, 1080), "square": (1080, 1080)}
W, H = SIZES.get(SPEC.get("size", "portrait"), None) or tuple(SPEC["size"])
TS = 512
TILED = SPEC.get("style", "amap") in ("amap", "amap-dark", "amap-gray", "amap-sepia", "satellite", "satellite-world")
ZMAX = 17.5 if TILED else 8.0          # 矢量样式的边界是抽稀过的（约 2 km 精度），推过 8 级海岸线就成了直线段；街道级用高德底图
_warned = []
camera, layers, T = [], [], 0.0
GEOM = []                           # 至今出现过的所有点，overview 用
_places = {}
SFX = []                            # 音效点（render.py 自动合成音轨）


# ---------- 工具
def place(p):
    """'深圳' | [lng,lat] | {"name": 显示名, "at": [lng,lat] 或 "地址"} → {lnglat, label}"""
    if isinstance(p, dict):
        at = p.get("at") or p.get("name")
        if isinstance(at, (list, tuple)) and p.get("wgs84"): at = amap.wgs2gcj(*at)          # GPS/照片 EXIF 坐标先转高德坐标
        g = amap.geocode(at); print(f"     地点 {p.get('name', '')}（{at}）→ {g['name']}（{g['level']}）{g['lnglat']}")
        return {"lnglat": g["lnglat"], "label": p.get("label", p.get("name", ""))}
    key = json.dumps(p, ensure_ascii=False)
    if key not in _places:
        g = amap.geocode(p); _places[key] = {"lnglat": g["lnglat"], "label": p if isinstance(p, str) else ""}
        print(f"     地点 {p} → {g['name']}（{g['level']}）{g['lnglat']}")         # 核对：同名地点可能解析错（如「香格里拉」→ 酒店）
    return _places[key]


def merc(ll):
    s = math.sin(math.radians(max(-85, min(85, ll[1]))))
    return (ll[0] + 180) / 360, 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


def unmerc(x, y): return [x * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y))))]


def fit(points, fw=0.72, fh=None, zmax=16.5, zmin=3.7, dy=0.0):
    """把这些点框进画面：fw/fh＝占画宽/画高的比例；dy＝内容中心相对画面中心下移的比例（给顶部标题让位）"""
    fh = fh or (0.42 if H > W else 0.62)
    ms = [merc(p) for p in points]; xs, ys = [m[0] for m in ms], [m[1] for m in ms]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    sx, sy = max(x1 - x0, 1e-7), max(y1 - y0, 1e-7)
    z = math.log2(min(W * fw / (sx * TS), H * fh / (sy * TS)))
    z = max(zmin, min(zmax, z))
    ww = TS * 2 ** z
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - dy * H / ww
    ll = unmerc(cx, cy); return {"lng": ll[0], "lat": ll[1], "zoom": round(z, 3)}


def cam_key(t, cam, ease="inOut"):
    if cam["zoom"] > ZMAX + 0.2:
        if not _warned: print(f"  ⚠ 样式 {SPEC.get('style')} 是矢量底图，镜头最多推到 {ZMAX} 级（要街道级细节换 amap / satellite）"); _warned.append(1)
        cam = {**cam, "zoom": ZMAX + 0.2}
    camera.append({"t": round(t, 3), "lng": round(cam["lng"], 6), "lat": round(cam["lat"], 6), "zoom": round(cam["zoom"], 3), "ease": ease})


def fly_to(cam, fly=None):
    """从当前相机飞到 cam；返回飞行用时。第一镜直接落位。"""
    global T
    if not camera: cam_key(0, cam); return 0
    a = camera[-1]
    if abs(a["zoom"] - cam["zoom"]) < 0.02 and abs(a["lng"] - cam["lng"]) < 1e-5 and abs(a["lat"] - cam["lat"]) < 1e-5: return 0
    if fly is None:
        ma, mb = merc([a["lng"], a["lat"]]), merc([cam["lng"], cam["lat"]])
        d = math.hypot(ma[0] - mb[0], ma[1] - mb[1]) * TS * 2 ** min(a["zoom"], cam["zoom"]) / W
        fly = max(1.0, min(3.2, 0.9 + 0.16 * abs(a["zoom"] - cam["zoom"]) + 0.55 * math.log2(1 + d)))
    if camera[-1]["t"] < T: cam_key(T, a, a.get("ease", "inOut"))
    cam_key(T + fly, cam, "fly"); T += fly; return fly


def hold(dur, push=0.12):
    """停在当前相机上 dur 秒，缓慢推近 push 级（画面一直在动）"""
    a = camera[-1]; cam_key(T + dur, {**a, "zoom": a["zoom"] + push}, "linear")


def add(**L):
    L = {k: v for k, v in L.items() if v is not None}
    if "t_out" in L and "t_end" not in L: L["t_end"] = round(L["t_out"] + 0.5, 3)
    for k in ("t0", "t1", "t_out", "t_end"):
        if k in L: L[k] = round(L[k], 3)
    layers.append(L); return L


def overlays(sh, t0, t1):
    if sh.get("title"):
        ti = sh["title"] if isinstance(sh["title"], dict) else {"text": sh["title"]}
        add(type="title", t0=t0, t_out=t1 - 0.35, **ti)
    if sh.get("caption"):
        ca = sh["caption"] if isinstance(sh["caption"], dict) else {"text": sh["caption"]}
        add(type="caption", t0=t0, t_out=t1 - 0.3, **ca)


def clear_map(t):
    for L in layers:
        if L["type"] in ("route", "pin", "region") and "t_out" not in L: L["t_out"] = t; L["t_end"] = t + 0.5


def img_path(p):
    f = (sp.parent / p).resolve()
    if not f.exists(): raise SystemExit(f"图片不存在：{p}")
    return str(Path(*([".."] * 0)) / f.relative_to(out.parent)) if out.parent in f.parents else str(f)


def great_circle(a, b, n=96):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    v1 = (math.cos(la1) * math.cos(lo1), math.cos(la1) * math.sin(lo1), math.sin(la1)); v2 = (math.cos(la2) * math.cos(lo2), math.cos(la2) * math.sin(lo2), math.sin(la2))
    om = math.acos(max(-1, min(1, sum(x * y for x, y in zip(v1, v2)))))
    if om < 1e-9: return [a, b]
    pts = []
    for i in range(n + 1):
        f = i / n; k1, k2 = math.sin((1 - f) * om) / math.sin(om), math.sin(f * om) / math.sin(om)
        x, y, z = (k1 * p + k2 * q for p, q in zip(v1, v2)); pts.append([round(math.degrees(math.atan2(y, x)), 5), round(math.degrees(math.atan2(z, math.hypot(x, y))), 5)])
    for i in range(1, len(pts)):                              # 跨 180° 经线时保持连续
        while pts[i][0] - pts[i - 1][0] > 180: pts[i][0] -= 360
        while pts[i][0] - pts[i - 1][0] < -180: pts[i][0] += 360
    return pts


def get_line(a, b, mode, via=None):
    if mode in ("arc", "line"): return {"line": great_circle(a, b) if mode == "arc" else [a, b], "km": round(haversine(a, b), 1), "hours": None}
    return amap.route(a, b, mode, via)


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    return 6371 * 2 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))


# ---------- 镜头
def shot_globe(sh):
    global T
    p = place(sh["to"]); ll = p["lnglat"]; dur = sh.get("dur", 6)
    zg = math.log2(0.82 * math.pi * min(W, H) / TS)                 # 地球直径约 0.82 画宽
    start = {"lng": ll[0] + sh.get("spin", -110), "lat": ll[1] * 0.3, "zoom": zg}
    if camera: fly_to(start, sh.get("fly", 1.2))
    else: cam_key(0, start)
    t0 = T
    cam_key(T + dur * 0.42, {"lng": ll[0], "lat": ll[1], "zoom": zg + 0.35}, "globe")
    end = {"lng": ll[0], "lat": ll[1], "zoom": sh.get("zoom", 11)}
    cam_key(T + dur, end, "smooth"); T += dur
    add(type="pin", t0=T - 0.9, lnglat=ll, label=sh.get("label", p["label"]), sub=sh.get("sub"), chip=True, kind=sh.get("pin"))
    GEOM.append(ll); overlays(sh, t0, T)
    hold(sh.get("hold", 1.5)); T += sh.get("hold", 1.5)


def shot_locate(sh):
    """Vlog「我在哪里」：地球俯冲 → 瞄准镜收缩锁定 → 坐标卡（地名打字、经纬度滚动、海拔、日期）"""
    global T
    p = place(sh["to"]); ll = p["lnglat"]; dur = sh.get("dur", 6.5)
    zg = math.log2(0.82 * math.pi * min(W, H) / TS)
    start = {"lng": ll[0] + sh.get("spin", -110), "lat": ll[1] * 0.3, "zoom": zg}
    if camera: fly_to(start, sh.get("fly", 1.2))
    else: cam_key(0, start)
    t0 = T
    cam_key(T + dur * 0.4, {"lng": ll[0], "lat": ll[1], "zoom": zg + 0.35}, "globe")
    cam_key(T + dur, {"lng": ll[0], "lat": ll[1], "zoom": sh.get("zoom", 15)}, "smooth"); T += dur
    alt = elev.at(*ll) if sh.get("altitude", True) else None
    if alt is not None: print(f"     海拔 {alt} m（SRTM 30m）")
    add(type="reticle", t0=T - 1.6, lock=1.4, color=sh.get("color"), t_out=T + sh.get("hold", 3.5) - 0.4 if sh.get("reticle_out", True) else None)
    add(type="pin", t0=T - 0.15, lnglat=ll, kind="dot", color=sh.get("color"))
    add(type="coordcard", t0=T - 0.1, lnglat=ll, name=sh.get("name", p["label"]), sub=sh.get("sub"), kicker=sh.get("kicker"), date=sh.get("date"), alt=alt, color=sh.get("color"),
        t_out=T + sh.get("hold", 3.5) - 0.3 if sh.get("card_out") else None)          # card_out：坐标卡在这一镜结束时收起（后面还有镜头时用）
    GEOM.append(ll); overlays(sh, t0, T)
    hold(sh.get("hold", 3.5), 0.25); T += sh.get("hold", 3.5)


def shot_pins(sh):
    global T
    ps = [place(x) for x in sh["places"]]; pts = [p["lnglat"] for p in ps]
    cam = fit(pts, dy=0.03) if len(pts) > 1 else {"lng": pts[0][0], "lat": pts[0][1], "zoom": sh.get("zoom", 12)}
    if sh.get("zoom") and len(pts) > 1: cam["zoom"] = sh["zoom"]
    fly_to(cam, sh.get("fly")); t0 = T; dur = sh.get("dur", 1.2 + 0.5 * len(ps))
    labels = sh.get("labels") or [p["label"] for p in ps]
    for i, (p, lb) in enumerate(zip(ps, labels)):
        add(type="pin", t0=T + 0.2 + i * sh.get("stagger", 0.45), lnglat=p["lnglat"], label=lb, chip=sh.get("chip", len(ps) <= 3), kind=sh.get("pin"))
    GEOM.extend(pts); overlays(sh, t0, T + dur); hold(dur); T += dur


def shot_route(sh, *, arc=False):
    global T
    tr = sh.get("track")
    if tr is not None:                                        # 自带轨迹：GPX / GeoJSON 文件（缺省按 WGS-84 转换）或坐标列表（缺省已是高德坐标）
        line = osm.track(sp.parent / tr, sh.get("wgs84", True)) if isinstance(tr, str) else ([amap.wgs2gcj(*q) for q in tr] if sh.get("wgs84") else tr)
        line = amap.simplify(line)
        a = place(sh["from"]) if sh.get("from") else {"lnglat": line[0], "label": ""}
        b = place(sh["to"]) if sh.get("to") else {"lnglat": line[-1], "label": ""}
        mode = sh.get("mode", "walking")
        r = {"line": line, "km": round(sum(haversine(line[i - 1], line[i]) for i in range(1, len(line))), 2), "hours": None}
    else:
        a, b = place(sh["from"]), place(sh["to"])
        mode = "arc" if arc else sh.get("mode", "driving")
        via = [place(v)["lnglat"] for v in sh.get("via", [])]
        r = get_line(a["lnglat"], b["lnglat"], mode, via or None)
    pts = r["line"]; cam = fit(pts + [a["lnglat"], b["lnglat"]], fh=(0.36 if H > W else 0.5) if mode == "arc" else None, dy=0.04 if mode == "arc" else 0.02)
    fly_to(cam, sh.get("fly")); t0 = T
    dur = sh.get("dur", max(3.0, min(8.0, 2.4 + 1.4 * math.log2(1 + r["km"] / 50))))
    vehicle = sh.get("vehicle", "plane" if mode == "arc" else {"driving": "car", "walking": "walk", "bicycling": "bike"}.get(mode, "dot"))
    if sh.get("pins", True):
        add(type="pin", t0=T, lnglat=a["lnglat"], label=sh.get("label_from", a["label"]), kind=sh.get("pin", "dot"))
    lay = add(type="route", t0=T + 0.3, t1=T + 0.3 + dur * 0.82, line=pts, arc=mode == "arc", vehicle=None if vehicle == "none" else vehicle,
              color=sh.get("color"), second=sh.get("second"), ghost=sh.get("ghost"), park=sh.get("park", True), width=sh.get("width"))
    if mode == "arc": lay["from"], lay["to"] = a["lnglat"], b["lnglat"]
    if sh.get("pins", True):
        add(type="pin", t0=T + 0.3 + dur * 0.82, lnglat=b["lnglat"], label=sh.get("label_to", b["label"]), kind=sh.get("pin_to", sh.get("pin", None)), chip=sh.get("chip", False))
    if sh.get("elevation"):
        pr = elev.profile(pts); print(f"     海拔 {pr['min']}–{pr['max']} m，累计爬升 {pr['gain']} m（SRTM 30m）")
        add(type="profile", t0=T + 0.3, t1=T + 0.3 + dur * 0.82, samples=pr["samples"], km=r["km"], t_out=T + dur - 0.3 if not sh.get("keep_profile") else None)
    if sh.get("follow"):
        n = max(4, int(dur * 2)); z = min(cam["zoom"] + sh.get("follow_zoom", 2.2), 16.5)
        for i in range(n + 1):
            f = i / n; e = f * f * (3 - 2 * f); idx = min(len(pts) - 1, int(e * (len(pts) - 1)))
            cam_key(T + 0.3 + dur * 0.82 * f, {"lng": pts[idx][0], "lat": pts[idx][1], "zoom": z}, "inOut" if i == 0 else "linear")
        cam_key(T + dur, cam, "inOut")
    else: hold(dur)
    if sh.get("odometer"):
        od = sh["odometer"] if isinstance(sh["odometer"], dict) else {}
        add(type="odometer", t0=T + 0.3, t1=T + 0.3 + dur * 0.82, to=r["km"] + od.get("from", 0), **{"from": od.get("from", 0)}, label=od.get("label"), t_out=T + dur - 0.3 if not od.get("keep") else None,
            decimals=2 if r["km"] + od.get("from", 0) < 10 else None)                 # 几百米的路取整会显示 0
    GEOM.extend([a["lnglat"], b["lnglat"]]); overlays(sh, t0, T + dur); T += dur
    return r


def shot_region(sh):
    global T
    regs = [amap.district(n) for n in sh["names"]]
    cam = fit([p for r in regs for ring in r["rings"] for p in ring], fw=0.8, dy=0.02)
    fly_to(cam, sh.get("fly")); t0 = T; st = sh.get("stagger", 1.0); dur = sh.get("dur", 2.0 + st * len(regs))
    cols = sh.get("colors") or [None] * len(regs)
    for i, r in enumerate(regs):
        add(type="region", t0=T + 0.2 + i * st, rings=r["rings"], center=r["center"], label=(sh.get("labels") or [r["name"]] * len(regs))[i],
            color=cols[i % len(cols)], draw=sh.get("draw", 1.2), opacity=sh.get("opacity"))
    GEOM.extend(r["center"] for r in regs); overlays(sh, t0, T + dur); hold(dur, 0.08); T += dur


def shot_area(sh):
    """任意地块（公园、景区、校园…）轮廓：描边 → 填色 → 写名；trace 时小人沿边界走一圈。"""
    global T
    p = place(sh.get("at") or sh["name"])
    if sh.get("rings"): rings = [[amap.wgs2gcj(*q) for q in r] for r in sh["rings"]] if sh.get("wgs84") else sh["rings"]; src = "spec"
    elif sh.get("geojson"): rings = [osm.track(sp.parent / sh["geojson"], sh.get("wgs84", True))]; src = sh["geojson"]
    else: a = osm.area(sh.get("osm_name", sh["name"]), p["lnglat"]); rings, src = a["rings"], a["source"]
    print(f"     地块 {sh['name']} ← {src}，{sum(len(r) for r in rings)} 个点")
    pts = [q for r in rings for q in r]
    cam = fit(pts, fw=sh.get("fw", 0.62), fh=0.34 if H > W else 0.55, dy=0.02)
    if sh.get("zoom"): cam["zoom"] = sh["zoom"]
    fly_to(cam, sh.get("fly")); t0 = T; dur = sh.get("dur", 4.0)
    ring = max(rings, key=len); ring = ring if ring[0] == ring[-1] else ring + [ring[0]]
    cx, cy = sum(q[0] for q in ring[:-1]) / (len(ring) - 1), sum(q[1] for q in ring[:-1]) / (len(ring) - 1)
    draw = dur * 0.62 if sh.get("trace") else sh.get("draw", 1.4)
    add(type="region", t0=T + 0.2, rings=rings, center=[cx, cy], label=sh.get("label", sh["name"]), color=sh.get("color"), draw=draw, opacity=sh.get("opacity"), width=sh.get("width", 6), size=sh.get("size"))
    if sh.get("trace"):
        per = round(sum(haversine(ring[i - 1], ring[i]) for i in range(1, len(ring))), 2)
        add(type="route", t0=T + 0.2, t1=T + 0.2 + draw, line=ring, vehicle=sh.get("vehicle", "walk"), hideLine=True, park=False, ease="linear" if sh.get("linear") else None)
        if sh.get("odometer", True): add(type="odometer", t0=T + 0.2, t1=T + 0.2 + draw, to=per, **{"from": 0}, label=sh.get("odometer_label", "绕一圈"), t_out=T + dur - 0.3, unit="km", decimals=2)
    GEOM.extend(pts); overlays(sh, t0, T + dur); hold(dur, 0.06); T += dur


def shot_radiate(sh):
    global T
    c0 = place(sh["from"]); ends = [place(x) for x in sh["to"]]
    cam = fit([c0["lnglat"]] + [e["lnglat"] for e in ends], fw=0.8, fh=0.48 if H > W else 0.66, dy=0.03)
    fly_to(cam, sh.get("fly")); t0 = T; dur = sh.get("dur", 4.5); st = sh.get("stagger", min(0.3, 2.0 / max(1, len(ends))))
    add(type="pin", t0=T, lnglat=c0["lnglat"], label=sh.get("label", c0["label"]), kind="dot", chip=True)
    for i, e in enumerate(ends):
        s = T + 0.4 + i * st
        add(type="route", t0=s, t1=s + sh.get("fly_time", 1.3), line=great_circle(c0["lnglat"], e["lnglat"], 48), arc=True, height=0.18,
            **{"from": c0["lnglat"]}, to=e["lnglat"], vehicle=None, width=sh.get("width", 4), second=bool(sh.get("second")), ease="inOut")
        add(type="pin", t0=s + sh.get("fly_time", 1.3) - 0.1, lnglat=e["lnglat"], label=e["label"] if sh.get("labels", True) else None, kind="dot", size=30)
    GEOM.extend([c0["lnglat"]] + [e["lnglat"] for e in ends]); overlays(sh, t0, T + dur); hold(dur, 0.06); T += dur


def shot_trip(sh):
    global T
    stops = [place(s) for s in sh["stops"]]; names = [s if isinstance(s, str) else s.get("name", "") for s in sh["stops"]]
    mode = sh.get("mode", "driving"); km = 0.0; photos = sh.get("photos", {}); dates = sh.get("dates", {}); stay = sh.get("stay", 2.6)
    legs = []
    for i in range(len(stops) - 1):
        r = get_line(stops[i]["lnglat"], stops[i + 1]["lnglat"], mode); legs.append(r)
    if sh.get("overview", True):
        cam = fit([p for r in legs for p in r["line"]], dy=0.04); fly_to(cam, sh.get("fly")); t0 = T
        add(type="pin", t0=T + 0.2, lnglat=stops[0]["lnglat"], label=names[0], kind="stamp" if sh.get("stamp") else None, stampSub=dates.get(names[0]))
        overlays(sh, t0, T + 2.2); hold(2.2, 0.05); T += 2.2
    for i, r in enumerate(legs):
        cam = fit(r["line"], fw=0.66, fh=0.34 if H > W else 0.55, dy=-0.05 if H > W else 0); fly_to(cam, 0.9)
        dur = sh.get("drive") or round(2.4 + 2.2 * math.sqrt(r["km"] / 760), 2); s = T
        add(type="route", t0=s, t1=s + dur, line=r["line"], vehicle=sh.get("vehicle", {"driving": "car", "walking": "walk", "bicycling": "bike"}.get(mode, "dot")), park=False, dash=sh.get("dash"))
        add(type="odometer", t0=s, t1=s + dur, to=km + r["km"], **{"from": km}, t_out=None if i == len(legs) - 1 else s + dur + stay - 0.01)
        if sh.get("elevation"):
            pr = elev.profile(r["line"], 80); print(f"     {names[i]}→{names[i + 1]} 海拔 {pr['min']}–{pr['max']} m，爬升 {pr['gain']} m")
            add(type="profile", t0=s, t1=s + dur, samples=pr["samples"], km=r["km"], t_out=s + dur + stay - 0.3)
        if i == len(legs) - 1: layers[-1].pop("t_out", None)
        d = dates.get(names[i + 1], ""); day = f"DAY {i + 1}" if sh.get("days", True) else ""
        add(type="caption", t0=s, t_out=s + dur + stay - 0.3, text=f"{names[i]} → {names[i + 1]}", sub=" · ".join(x for x in (day, d, f"{r['km']} km") if x))
        km += r["km"]; hold(dur, 0.08); T += dur
        add(type="pin", t0=T, lnglat=stops[i + 1]["lnglat"], label=names[i + 1], kind="stamp" if sh.get("stamp") else None, stampSub=d)
        sc = {**camera[-1]}; cam_key(T + stay, {**sc, "zoom": sc["zoom"] + 0.15}, "inOut")
        for k, im in enumerate(photos.get(names[i + 1], [])[:2]):
            pi = im if isinstance(im, dict) else {"image": im}
            add(type="photo", t0=T + 0.3 + 0.5 * k, t_out=T + stay - 0.3, image=img_path(pi["image"]), caption=pi.get("caption", f"{names[i + 1]}{(' · ' + d) if d else ''}"), slot=k)
        T += stay
    GEOM.extend(s["lnglat"] for s in stops)
    if sh.get("return"):
        tot = sum(r["km"] for r in legs); s = T; cam = fit([p for r in legs for p in r["line"]], dy=0.04); fly_to(cam, 1.2); s = T; dur = sh.get("return_dur", 5)
        back = [p for r in reversed(legs) for p in reversed(r["line"])]
        add(type="route", t0=s, t1=s + dur, line=back, vehicle=sh.get("vehicle", "car"), second=True, dash=[10, 12], park=True)
        add(type="odometer", t0=s, t1=s + dur, to=km + tot, **{"from": km}); km += tot
        add(type="caption", t0=s, t_out=s + dur, text="原路返程", sub=f"{names[-1]} → {names[0]} · {round(tot)} km")
        hold(dur, 0.05); T += dur
    return km


def shot_guess(sh):
    """「这张照片在哪拍的？」：整屏照片＋问题＋提示＋倒数，照片缩走露出地球；镜头停在下一镜 locate/globe 的起点，衔接无跳变"""
    global T
    p = place(sh["to"]); ll = p["lnglat"]; dur = sh.get("dur", 6.5)
    zg = math.log2(0.82 * math.pi * min(W, H) / TS)
    end = {"lng": ll[0] + sh.get("spin", -110), "lat": ll[1] * 0.3, "zoom": zg}; start = {**end, "lng": end["lng"] - 8}   # 照片后面地球朝目标方向缓慢转，转到下一镜的起点
    if camera: fly_to(start, sh.get("fly", 1.0))
    else: cam_key(0, start)
    hints = sh.get("hints", []); cd = sh.get("count", 3)
    add(type="quiz", t0=T, t_out=T + dur - 0.6, image=img_path(sh["image"]), text=sh.get("text", "这张照片在哪拍的？"), sub=sh.get("sub"), kicker=sh.get("kicker", "GUESS WHERE"),
        hints=hints, hint_t=[round(1.0 + 0.7 * k, 3) for k in range(len(hints))], count=cd, count_t0=round(dur - 0.6 - cd, 3), color=sh.get("color"))
    cam_key(T + dur, end, "linear"); T += dur


def shot_snap(sh):
    """「咔嚓」：地球俯冲 → 落出机位（相机图标）和被摄地点 → 取景扇形从机位扫向被摄地 → 取景框对焦 → 快门（音效）→ 照片从机位处翻折立起，背景是虚化的当地地图"""
    global T
    a = place(sh["camera"]); b = place(sh["target"]); A_, B_ = a["lnglat"], b["lnglat"]; dur = sh.get("dur", 6)
    zg = math.log2(0.82 * math.pi * min(W, H) / TS); mid = [(A_[0] + B_[0]) / 2, (A_[1] + B_[1]) / 2]
    start = {"lng": mid[0] + sh.get("spin", -110), "lat": mid[1] * 0.3, "zoom": zg}
    if camera: fly_to(start, sh.get("fly", 1.2))
    else: cam_key(0, start)
    t0 = T
    cam_key(T + dur * 0.42, {"lng": mid[0], "lat": mid[1], "zoom": zg + 0.35}, "globe")
    end = fit([A_, B_], fw=sh.get("frame", 0.5), fh=sh.get("frame", 0.5) * 0.72, zmax=sh.get("zoom", 15)); cam_key(T + dur, end, "smooth"); T += dur
    add(type="pin", t0=T - 0.5, lnglat=A_, kind="camera", label=sh.get("camera_label", a["label"] or "机位"), chip=True, color=sh.get("color"))
    add(type="pin", t0=T - 0.15, lnglat=B_, label=sh.get("target_label", b["label"]), sub=sh.get("target_sub"), chip=True, color=sh.get("color"))
    add(type="cone", t0=T + 0.1, draw=1.0, a=A_, b=B_, fov=sh.get("fov", 34), color=sh.get("color"))
    focus = sh.get("focus", 1.6); ts = T + 1.1 + focus                         # 扇形画完 → 取景框对焦 focus 秒 → 快门
    km = haversine(A_, B_)
    add(type="snap", t0=T + 1.1, ts=round(ts, 3), image=img_path(sh["image"]), anchor=A_, name=sh.get("name"), sub=sh.get("sub", f"距{b['label'] or '被摄地'} {km:.0f} km"),
        exif=sh.get("exif", "ISO 100   1/1000   f/8   200mm"), lnglat=A_, color=sh.get("color"))
    SFX.append({"t": round(ts, 3), "type": "shutter"})
    hold_ = sh.get("hold", 4.0)
    if sh.get("live"):                                                       # Live Photo：相纸立起后「按住」播放一段动态
        lv = snap_live(sh["live"]); lt0 = sh.get("live_at", 1.9)
        layers[-1].update(live=True, live_t=lt0, live_dur=lv["dur"], frames=lv.get("frames"))
        if lv.get("audio"): SFX.append({"t": round(ts + lt0, 3), "type": "clip", "path": lv["audio"], "dur": lv["dur"]})
        hold_ = max(hold_, lt0 + lv["dur"] + 1.6)
    GEOM.extend([A_, B_]); overlays(sh, t0, T)
    tail = 1.1 + focus + hold_; hold(tail, 0.18); T += tail


def snap_live(v):
    """live: true＝用静态照片模拟（推近＋手持晃动＋首尾虚化）；"x.mov"＝真 Live Photo 视频：抽帧（最长 3 秒、30fps）并带上原声"""
    if v is True: return {"dur": 2.4}
    import subprocess
    f = (sp.parent / v).resolve()
    if not f.exists(): raise SystemExit(f"Live 视频不存在：{v}")
    d = out.parent / f"{sp.stem}.live"; d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.jpg"): old.unlink()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(f), "-t", "3", "-vf", "fps=30,scale='min(1080,iw)':-2", "-q:v", "3", str(d / "%04d.jpg")], check=True)
    fr = sorted(d.glob("*.jpg")); print(f"     Live 视频 {f.name} → {len(fr)} 帧")
    has_a = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(f)], capture_output=True, text=True).stdout.strip()
    return {"dur": round(len(fr) / 30, 3), "frames": [img_path(str(x)) for x in fr], "audio": str(f) if has_a else None}


def shot_overview(sh):
    global T
    cam = fit(GEOM or [[105, 35]], fw=0.78, dy=0.03); fly_to(cam, sh.get("fly")); t0 = T; dur = sh.get("dur", 2.5)
    overlays(sh, t0, T + dur); hold(dur, 0.06); T += dur


def shot_title(sh):
    global T
    dur = sh.get("dur", 2.5); ti = {"text": sh["text"], "sub": sh.get("sub"), "pos": sh.get("pos", "center"), "size": sh.get("size")}
    add(type="title", t0=T, t_out=T + dur - 0.35, **{k: v for k, v in ti.items() if v is not None}); hold(dur, 0.05); T += dur


SHOTS = {"globe": shot_globe, "locate": shot_locate, "pins": shot_pins, "route": shot_route, "flight": lambda s: shot_route(s, arc=True), "region": shot_region,
         "radiate": shot_radiate, "area": shot_area, "trip": shot_trip, "overview": shot_overview, "title": shot_title, "guess": shot_guess, "snap": shot_snap}
for i, sh in enumerate(SPEC["shots"]):
    for L in layers:                                          # 新镜头开始：旧落点只留点，字淡出（拉远后不挤成一团）
        if L["type"] == "pin" and "label_out" not in L and L["t0"] < T: L["label_out"] = round(T, 3)
    if sh.get("clear"): clear_map(T)                          # 任何镜头都能清场：之前的路线/落点/区域淡出
    fn = SHOTS.get(sh["type"])
    if not fn: raise SystemExit(f"第 {i + 1} 镜：不认识的 type「{sh['type']}」（可用：{'、'.join(SHOTS)}）")
    if not camera and sh["type"] == "title": cam_key(0, fit([[105, 35]], zmin=3.7, zmax=3.7) | {"zoom": 3.8})
    fn(sh)
    print(f"  {i + 1:>2}. {sh['type']:<8} 到 {T:6.2f}s")

tl = {"width": W, "height": H, "fps": SPEC.get("fps", 30), "style": SPEC.get("style", "amap"), "duration": round(T + SPEC.get("tail", 0.6), 3),
      "attribution": SPEC.get("attribution", True), "camera": camera, "layers": layers, "sfx": SFX}
cam_key(tl["duration"], {**camera[-1], "zoom": camera[-1]["zoom"] + 0.02}, "linear")
out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(tl, ensure_ascii=False))
print(f"timeline -> {out}  {tl['duration']}s  {W}×{H}  样式 {tl['style']}  图层 {len(layers)}  相机关键帧 {len(camera)}")
