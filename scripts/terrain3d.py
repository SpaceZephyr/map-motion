"""3D 地形轨迹片：spec（"mode": "3d"）→ timeline（runtime: terrain，逐帧相机都算好）。由 compile.py 转进来。

画面：卫星地球俯冲 → 整条轨迹的 3D 鸟瞰（白线 + 标题）→ 压低镜头贴到起点 → 跟着人沿轨迹走（黄线、里程、海拔、爬升、
小地图、底部海拔剖面；走到照片点停一下弹出照片）→ 拉回全景、绕一圈、出总数据。
坐标一律 WGS-84（GPX、OSM、Esri 卫星、地形瓦片都是）；高德解析出的点（GCJ）在这里转回 WGS。
"""
import json, math
from pathlib import Path
import amap, osm, elev, dem

R_EARTH = 6371.0


def hav(a, b):
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    return 2 * R_EARTH * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2))


def bearing(a, b):
    la1, la2, dl = math.radians(a[1]), math.radians(b[1]), math.radians(b[0] - a[0])
    return math.degrees(math.atan2(math.sin(dl) * math.cos(la2), math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl))) % 360


def merc(ll):
    s = math.sin(math.radians(max(-85, min(85, ll[1]))))
    return [(ll[0] + 180) / 360, 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)]


def smooth(p): p = max(0.0, min(1.0, p)); return p * p * p * (p * (6 * p - 15) + 10)
def inout(p): p = max(0.0, min(1.0, p)); return -(math.cos(math.pi * p) - 1) / 2
def lerp(a, b, e): return a + (b - a) * e
def lerp_ang(a, b, e): return a + ((b - a + 540) % 360 - 180) * e


def compile(SPEC, sp, out, W, H):
    gcj_in = SPEC.get("gcj", False)

    def pt(p):
        """[lng,lat]（WGS，"gcj": true 时按高德坐标）| "地名" | {"name","at"} → WGS [lng,lat]"""
        if isinstance(p, dict): p = p.get("at") or p.get("name")
        if isinstance(p, str):
            g = amap.geocode(p); print(f"     地点 {p} → {g['name']}（{g['level']}）"); return elev.gcj2wgs(*g["lnglat"])
        return elev.gcj2wgs(*p) if gcj_in else list(p)

    def gcj_pt(p):
        """同上，但给高德路线规划用：返回 GCJ-02"""
        if isinstance(p, dict): p = p.get("at") or p.get("name")
        if isinstance(p, str):
            g = amap.geocode(p); print(f"     地点 {p} → {g['name']}（{g['level']}）{g['lnglat']}"); return g["lnglat"]
        return list(p) if gcj_in else amap.wgs2gcj(*p)

    if SPEC.get("place") and not SPEC.get("track"): return compile_place(SPEC, pt, out, W, H)

    # ---------- 轨迹
    tr = SPEC["track"]
    if isinstance(tr, dict) and tr.get("from"):                                   # 高德路线规划：驾车/步行/骑行
        mode = tr.get("mode", "driving")
        r = amap.route(gcj_pt(tr["from"]), gcj_pt(tr["to"]), mode, [gcj_pt(v) for v in tr.get("via", [])] or None)
        line = [elev.gcj2wgs(*q) for q in r["line"]]; src = f"高德{ {'driving': '驾车', 'walking': '步行', 'bicycling': '骑行'}.get(mode, mode)}路线"
    elif isinstance(tr, str):
        f = (sp.parent / tr).resolve(); line = osm.track(f, wgs84=False)                    # GPX/GeoJSON 本身就是 WGS，不转
        src = f"轨迹文件 {f.name}"
    elif isinstance(tr, dict) and tr.get("via"):
        line = osm.trail([pt(p) for p in tr["via"]], margin=tr.get("margin", 0.02)); src = "OSM 小路连线（途经点之间取最短路）"
    else:
        line = [pt(p) for p in tr]; src = "spec 里的坐标"
    line = [p for i, p in enumerate(line) if i == 0 or hav(p, line[i - 1]) > 0.001]
    cum = [0.0]
    for a, b in zip(line, line[1:]): cum.append(cum[-1] + hav(a, b))
    L = cum[-1]
    if L < 0.2: raise SystemExit("轨迹太短（< 200 m）")
    S = max(1.0, L / 12) ** 0.85                                                  # 长路线（自驾几百公里）时，看前方的距离、平滑窗口一起放大
    step = max(0.01, L / 3000)                                                   # 均匀重采样：10 m 一点（长轨迹最多 3000 点）
    n = int(L / step) + 1; P, j = [], 1
    for k in range(n + 1):
        d = min(L, k * step)
        while j < len(cum) - 1 and cum[j] < d: j += 1
        f = (d - cum[j - 1]) / max(1e-12, cum[j] - cum[j - 1]); a, b = line[j - 1], line[j]
        P.append([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, d])
    zd = 13 if L < 40 else 12 if L < 150 else 11
    raw = [dem.at(p[0], p[1], zd) for p in P]
    w = max(1, int(0.06 * S / step))                                                 # ±60 m 平滑，去掉 DEM 台阶
    ele = [sum(raw[max(0, i - w):i + w + 1]) / len(raw[max(0, i - w):i + w + 1]) for i in range(len(raw))]
    gain, ref, G = 0.0, ele[0], []
    for e in ele:                                                                # 3 m 滞回算累计爬升
        if e > ref + 3: gain += e - ref; ref = e
        elif e < ref - 3: ref = e
        G.append(gain)
    loss = sum(max(0, ele[i - 1] - ele[i]) for i in range(1, len(ele)))
    print(f"     轨迹 {src}：{L:.2f} km，海拔 {min(ele):.0f}–{max(ele):.0f} m，累计爬升 {gain:.0f} m（AWS Terrain Tiles）")

    def at_km(d):
        i = max(0, min(len(P) - 2, int(d / step))); f = max(0.0, min(1.0, (d - P[i][2]) / step))
        return [lerp(P[i][0], P[i + 1][0], f), lerp(P[i][1], P[i + 1][1], f)]

    def km_of(ll):
        return min(P, key=lambda p: hav(p, ll))[2]

    # ---------- 照片、地名
    photos = []
    for ph in SPEC.get("photos", []):
        d = ph["km"] if "km" in ph else km_of(pt(ph["at"]))
        photos.append({"type": "photo", "image": ph["image"], "km": round(d, 3), "label": ph.get("label", ""), "at": at_km(d)})
    photos.sort(key=lambda p: p["km"])
    marks = []
    for m in SPEC.get("marks", []):
        ll = pt(m); marks.append({"name": m["name"] if isinstance(m, dict) else m, "sub": m.get("sub", "") if isinstance(m, dict) else "", "at": ll,
                                  "ele": round(dem.at(*ll)) if (isinstance(m, dict) and m.get("ele")) else None})

    # ---------- 节奏
    fps = SPEC.get("fps", 30)
    D_DIVE, D_OV, D_SWOOP = SPEC.get("dive", 6.0), SPEC.get("overview", 2.6), SPEC.get("swoop", 2.4)
    D_FOLLOW = SPEC.get("follow", max(10.0, min(26.0, 8 + L * 0.9)))
    D_PAUSE = SPEC.get("pause", 2.2); D_END = SPEC.get("end", 6.0)
    zf, pf = SPEC.get("zoom", round(15.1 - min(3.4, max(0.0, math.log2(L / 12))), 2)), SPEC.get("pitch", 62)
    spin = SPEC.get("spin", -70)

    # 跟随段：按照片点分腿，每腿梯形速度（起步加速、到点减速）
    stops = [0.0] + [p["km"] for p in photos if 0.05 * S < p["km"] < L - 0.05 * S] + [L]
    legs = list(zip(stops, stops[1:]))
    t_f0 = D_DIVE + D_OV + D_SWOOP
    sched, t = [], t_f0                                                           # [(t0, t1, d0, d1)]
    for i, (a, b) in enumerate(legs):
        dt = D_FOLLOW * (b - a) / L; sched.append((t, t + dt, a, b)); t += dt
        if i < len(legs) - 1: sched.append((t, t + D_PAUSE, b, b)); t += D_PAUSE
    t_f1 = t; T_END = t_f1 + D_END + SPEC.get("tail", 0.4)

    def prog(t):
        if t <= t_f0: return 0.0
        for t0, t1, a, b in sched:
            if t <= t1:
                if a == b: return a
                T_, u = t1 - t0, t - t0; r = min(0.9, T_ / 3); v = 1 / (T_ - r)          # 归一化：加速 r、匀速、减速 r
                if u < r: s = v * u * u / (2 * r)
                elif u > T_ - r: s = 1 - v * (T_ - u) ** 2 / (2 * r)
                else: s = v * (u - r / 2)
                return a + (b - a) * s
        return L
    for p in photos:
        p["t_hit"] = round(next((t1 for t0, t1, a, b in sched if a != b and abs(b - p["km"]) < 1e-6), t_f0 if p["km"] <= 0.05 else t_f1), 3)

    # 跟随镜头的朝向：看向前方 400 m，再按时间做零相位高斯平滑（不追每个之字弯）
    la = min(0.4 * S, L * 0.3)
    def head(d): return bearing(at_km(max(0, d - la * 0.4)), at_km(min(L, d + la))) if L - d > la * 0.15 else bearing(at_km(L - la), at_km(L))
    def cen(d): return [sum(at_km(max(0, min(L, d + o * S))) [k] for o in (-0.12, -0.06, 0, 0.06, 0.12)) / 5 for k in (0, 1)]
    N = int(round(T_END * fps)) + 1
    ts = [i / fps for i in range(N)]; ds = [prog(t) for t in ts]
    fi0, fi1 = int(t_f0 * fps), min(N - 1, int(t_f1 * fps))
    hb = [head(ds[i]) for i in range(fi0, fi1 + 1)]
    for i in range(1, len(hb)): hb[i] = hb[i - 1] + ((hb[i] - hb[i - 1] + 540) % 360 - 180)        # 解卷绕
    sg = 1.1 * fps; K = [math.exp(-0.5 * (k / sg) ** 2) for k in range(-int(3 * sg), int(3 * sg) + 1)]; kh = len(K) // 2
    hs = [sum(hb[max(0, min(len(hb) - 1, i + k - kh))] * K[k] for k in range(len(K))) / sum(K) for i in range(len(hb))]

    def follow_cam(i):
        k = max(0, min(len(hs) - 1, i - fi0)); return {"c": cen(ds[i]), "z": zf, "p": pf, "b": hs[k] % 360}

    def fit_cam(b, pitch, fw=0.8, fh=0.55, pts=None):
        pts = pts or P[::max(1, len(P) // 400)]
        ms = [merc(p) for p in pts]; cx = sum(m[0] for m in ms) / len(ms); cy = sum(m[1] for m in ms) / len(ms)
        rb = math.radians(b); xs, ys = [], []
        for m in ms:
            dx, dy = m[0] - cx, m[1] - cy
            xs.append(dx * math.cos(rb) + dy * math.sin(rb)); ys.append(-dx * math.sin(rb) + dy * math.cos(rb))
        bw, bh = (max(xs) - min(xs)) or 1e-6, ((max(ys) - min(ys)) or 1e-6) * math.cos(math.radians(pitch)) * 1.15
        z = math.log2(min(W * fw / (bw * 512), H * fh / (bh * 512)))
        mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2                    # 旋转框中心换回墨卡托
        cxm = cx + mx * math.cos(rb) - my * math.sin(rb); cym = cy + mx * math.sin(rb) + my * math.cos(rb)
        lng = cxm * 360 - 180; lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * cym))))
        return {"c": [lng, lat], "z": min(z, zf - 1.0), "p": pitch, "b": b % 360}

    def best_cam(pref, pitch, fw, fh, span=70):
        """在 pref ±span 里挑能把整条轨迹放得最大的朝向（竖屏里轨迹顺着视线方向摆最舒服）；透视近大远小，再退 0.35 级"""
        cs = [fit_cam(pref + o, pitch, fw, fh) for o in range(-span, span + 1, 10)]
        k = max(cs, key=lambda cm: cm["z"] - 0.002 * abs(((cm["b"] - pref + 540) % 360) - 180)); k["z"] -= 0.35; return k

    b0 = hs[0] % 360
    ov = best_cam(b0, SPEC.get("overview_pitch", 44), 0.7, 0.5)
    ov_end = {**ov, "b": (ov["b"] + 8) % 360}
    fin = best_cam(hs[-1] % 360, 40, 0.66, 0.42); fin_b = fin["b"]
    st_ll = ov["c"]
    cams = []
    for i, t in enumerate(ts):
        if t < D_DIVE:                                                             # 地球俯冲
            u = t / D_DIVE; e = inout(u); ce = smooth(u / 0.85)
            cam = {"c": [st_ll[0] + spin * (1 - ce), lerp(st_ll[1] * 0.4, st_ll[1], ce)], "z": lerp(1.4, ov["z"], e ** 1.15),
                   "p": lerp(0, ov["p"], smooth((u - 0.55) / 0.45)), "b": lerp_ang(0, ov["b"], smooth((u - 0.5) / 0.5))}
        elif t < D_DIVE + D_OV:                                                    # 全景停留，慢转
            u = (t - D_DIVE) / D_OV; cam = {**ov, "b": lerp_ang(ov["b"], ov_end["b"], u)}
        elif t < t_f0:                                                             # 压低贴近起点
            u = smooth((t - D_DIVE - D_OV) / D_SWOOP); fc = follow_cam(fi0)
            cam = {"c": [lerp(ov["c"][0], fc["c"][0], u), lerp(ov["c"][1], fc["c"][1], u)], "z": lerp(ov["z"], fc["z"], inout(u)),
                   "p": lerp(ov["p"], fc["p"], u), "b": lerp_ang(ov_end["b"], fc["b"], u)}
        elif i <= fi1:
            cam = follow_cam(i)
        else:                                                                      # 拉回全景，绕一点
            u = (t - t_f1) / D_END; fc = follow_cam(fi1); e = smooth(u / 0.45)
            cam = {"c": [lerp(fc["c"][0], fin["c"][0], e), lerp(fc["c"][1], fin["c"][1], e)], "z": lerp(fc["z"], fin["z"], inout(u / 0.45)),
                   "p": lerp(fc["p"], fin["p"], e), "b": lerp_ang(fc["b"], fin_b, e) + 10 * smooth((u - 0.3) / 0.7)}
        cams.append([round(cam["c"][0], 6), round(cam["c"][1], 6), round(cam["z"], 4), round(cam["p"], 2), round(cam["b"] % 360, 2), round(ds[i], 4)])

    tl = {"runtime": "terrain", "width": W, "height": H, "fps": fps, "duration": round(T_END, 3),
          "title": SPEC.get("title", ""), "sub": SPEC.get("sub", ""), "exaggeration": SPEC.get("exaggeration", 1.35),
          "color": SPEC.get("color", "#f2ee3a"), "hud": SPEC.get("hud", True),
          "phase": {"dive": D_DIVE, "ov": D_DIVE + D_OV, "f0": t_f0, "f1": round(t_f1, 3), "end": round(T_END, 3)},
          "track": [[round(p[0], 6), round(p[1], 6), round(ele[i], 1), round(p[2], 4), round(G[i])] for i, p in enumerate(P)],
          "stats": {"km": round(L, 2), "gain": round(gain), "loss": round(loss), "max": round(max(ele)), "min": round(min(ele))},
          "marks": marks, "layers": photos, "frames": cams, "sfx": [],
          "attribution": "Imagery © Esri, Maxar, Earthstar Geographics · Terrain © Mapzen, AWS" + (" · Track © OpenStreetMap" if isinstance(tr, dict) else "")}
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(tl, ensure_ascii=False))
    print(f"timeline -> {out}  {tl['duration']}s  {W}×{H}  3D 地形  {len(cams)} 帧  照片 {len(photos)}  跟随 {t_f0:.1f}–{t_f1:.1f}s")


def compile_place(SPEC, pt, out, W, H):
    """只有一个地点（没有路线）：地球俯冲 → 压低成 3D 鸟瞰 → 绕着它转一圈，底部出地名、坐标、海拔"""
    ll = pt(SPEC["place"]); ele = SPEC.get("ele") or dem.at(*ll)                       # 山顶 DEM 偏低（30 m 网格削峰），已知海拔就写 ele
    fps = SPEC.get("fps", 30); D_DIVE, D_ORB = SPEC.get("dive", 6.0), SPEC.get("orbit", 8.0)
    z, pitch, spin = SPEC.get("zoom", 13.2), SPEC.get("pitch", 60), SPEC.get("spin", -70)
    b0, turn = SPEC.get("bearing", 0), SPEC.get("turn", 90)
    T_END = D_DIVE + D_ORB + SPEC.get("tail", 0.4); N = int(round(T_END * fps)) + 1; cams = []
    for i in range(N):
        t = i / fps
        if t < D_DIVE:
            u = t / D_DIVE; e = inout(u); ce = smooth(u / 0.85)
            cam = [ll[0] + spin * (1 - ce), lerp(ll[1] * 0.4, ll[1], ce), lerp(1.4, z, e ** 1.15), lerp(0, pitch, smooth((u - 0.55) / 0.45)), lerp_ang(0, b0, smooth((u - 0.5) / 0.5))]
        else:
            u = (t - D_DIVE) / D_ORB; cam = [ll[0], ll[1], z + 0.25 * smooth(u), pitch, b0 + turn * (0.15 * u + 0.85 * smooth(u))]
        cams.append([round(cam[0], 6), round(cam[1], 6), round(cam[2], 4), round(cam[3], 2), round(cam[4] % 360, 2), 0])
    marks = [{"name": m["name"], "sub": "", "at": pt(m), "ele": None} for m in SPEC.get("marks", [])]
    tl = {"runtime": "terrain", "place": {"name": SPEC.get("name", SPEC["place"] if isinstance(SPEC["place"], str) else ""), "at": ll, "ele": round(ele)},
          "width": W, "height": H, "fps": fps, "duration": round(T_END, 3), "title": SPEC.get("title", ""), "sub": SPEC.get("sub", ""),
          "exaggeration": SPEC.get("exaggeration", 1.35), "color": SPEC.get("color", "#f2ee3a"), "hud": False,
          "phase": {"dive": D_DIVE, "ov": D_DIVE, "f0": 1e9, "f1": 1e9, "end": round(T_END, 3)},
          "track": [[ll[0], ll[1], round(ele), 0, 0], [ll[0], ll[1], round(ele), 0.001, 0]],
          "stats": {"km": 0.001, "gain": 0, "loss": 0, "max": round(ele), "min": round(ele)},
          "marks": marks, "layers": [], "frames": cams, "sfx": [], "attribution": "Imagery © Esri, Maxar, Earthstar Geographics · Terrain © Mapzen, AWS"}
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(tl, ensure_ascii=False))
    print(f"     地点 {ll}（WGS-84）海拔 {ele:.0f} m")
    print(f"timeline -> {out}  {tl['duration']}s  {W}×{H}  3D 地形 · 单点环绕  {N} 帧")
