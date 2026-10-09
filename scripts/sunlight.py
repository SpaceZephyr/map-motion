"""光线规划片：spec（"mode": "sun"）→ timeline（runtime: terrain，和 3D 地形片同一个运行时 t3d.js）。由 compile.py 转进来。

画面：地球俯冲到目标山峰 → 从机位方向看山，时间快进（日出前后 / 日落前后）：山体明暗随太阳方位、高度变化，天空变色，
太阳方向射线、机位→山峰视线画在地形上，顶部时钟 + 罗盘（太阳方位、高度），关键时刻到点打勾 → 拉远出总表。
关键时刻都是算出来的（sun.py：NOAA 太阳位置 + AWS 高程沿太阳方向找地平线），不是查来的：
  天文日出/日落、山峰受光（日照金山开始）/最后一缕光、金色褪去（太阳高度 5°）、机位见光/没光。
"""
import json, math
from datetime import date
import dem, geo, sun
from geo import bearing, hav, smooth, inout, lerp, lerp_ang, ATTR


def compile(SPEC, sp, out, W, H):
    gcj = SPEC.get("gcj", False)
    peak = geo.resolve(SPEC["peak"], gcj); pname = SPEC.get("name") or (SPEC["peak"] if isinstance(SPEC["peak"], str) else SPEC["peak"].get("name", "") if isinstance(SPEC["peak"], dict) else "")
    pele = SPEC.get("ele") or dem.at(*peak)                                          # 山顶 DEM 会被削低，已知海拔就写 ele
    spot = geo.resolve(SPEC["spot"], gcj) if SPEC.get("spot") else None
    sname = (SPEC["spot"].get("name") if isinstance(SPEC.get("spot"), dict) else SPEC.get("spot") if isinstance(SPEC.get("spot"), str) else "机位") if spot else ""
    day = date.fromisoformat(SPEC["date"]); tz = SPEC.get("tz", 8); rise = SPEC.get("event", "sunrise") == "sunrise"

    pos = lambda m, ll=peak: sun.position(ll[0], ll[1], day, m, tz)
    hz_peak = sun.Horizon(peak, pele + 5)
    hz_spot = sun.Horizon(spot, dem.at(*spot) + 2) if spot else None
    lit = lambda hz, ll: (lambda m: (lambda az, al: al + sun.LIMB - hz(az))(*pos(m, ll)))
    lo, hi = (0, 760) if rise else (680, 1440)
    t_sun = sun.crossing(lambda m: pos(m)[1] + sun.LIMB, lo, hi, rising=rise)
    if t_sun is None: raise SystemExit("这天这里没有日出/日落（极昼/极夜）")
    t_peak = sun.crossing(lit(hz_peak, peak), lo, hi, rising=rise)
    t_gold = sun.crossing(lambda m: pos(m)[1] - 5, lo, hi, rising=rise)            # 太阳高度 5°：金色基本褪去（日落时是开始变金）
    t_spot = sun.crossing(lit(hz_spot, spot), lo, hi, rising=rise) if spot else None
    if t_peak is None: raise SystemExit(f"{pname} 这天{'早上' if rise else '傍晚'}照不到太阳（被更高的山挡住）")

    ev = [("天文日出" if rise else "天文日落", t_sun, f"方位 {pos(t_sun)[0]:.0f}°")]
    if rise:
        ev += [(f"{pname} 受光", t_peak, "日照金山开始"), ("金色褪去", t_gold, "太阳高度 5°")]
        if spot: ev.append((f"{sname} 见光", t_spot, f"山体挡到 {hz_spot(pos(t_spot, spot)[0]):.0f}°") if t_spot else (f"{sname} 上午不见光", None, ""))
    else:
        ev += [("开始变金", t_gold, "太阳高度 5°"), (f"{pname} 最后一缕光", t_peak, "日照金山结束")]
        if spot: ev.append((f"{sname} 没光", t_spot, f"山体挡到 {hz_spot(pos(t_spot, spot)[0]):.0f}°") if t_spot else (f"{sname} 一直有光", None, ""))
    ev.sort(key=lambda e: e[1] if e[1] is not None else 1e9)
    for n, m, note in ev: print(f"     ☀ {n:<14} {sun.hhmm(m) if m is not None else '—':>6}  {note}")

    ts_ = [m for _, m, _ in ev if m is not None]
    m0 = SPEC.get("from_min", min(ts_) - 22); m1 = SPEC.get("to_min", max(ts_) + 12)
    if m1 - m0 > 240: m0, m1 = (t_peak - 25, t_peak + 200) if rise else (t_peak - 200, t_peak + 25)    # 机位很久之后才见光：时间窗别拉太长
    print(f"     光线 {day} {'日出' if rise else '日落'}：快进 {sun.hhmm(m0)}–{sun.hhmm(m1)}（{m1 - m0:.0f} 分钟）")

    # ---------- 镜头
    fps = SPEC.get("fps", 30); D_DIVE, D_LAPSE, D_END = SPEC.get("dive", 6.0), SPEC.get("lapse", 14.0), SPEC.get("end", 5.0)
    b_view = SPEC.get("bearing", bearing(spot, peak) if spot else (pos(t_peak)[0] + 180) % 360)        # 背对太阳看受光面
    z, pitch = SPEC.get("zoom", 12.6), SPEC.get("pitch", 70)
    view = {"c": peak, "z": z, "p": pitch, "b": b_view}
    if spot:
        fin = geo.fit_cam([spot, peak, geo.dest(peak, (b_view + 90) % 360, hav(spot, peak) * 0.25), geo.dest(peak, (b_view - 90) % 360, hav(spot, peak) * 0.25)],
                          b_view, 52, W, H, 0.8, 0.42, z - 0.6); fin["z"] -= 0.3
    else:
        fin = {"c": peak, "z": z - 0.8, "p": 55, "b": b_view + 12}
    keys = [m for _, m, _ in ev if m is not None and m0 <= m <= m1]               # 时钟变速：关键时刻附近慢放，其余快进
    grid = [m0 + (m1 - m0) * k / 2000 for k in range(2001)]
    cw = [0.0]
    for a, b in zip(grid, grid[1:]):
        mm = (a + b) / 2; cw.append(cw[-1] + (b - a) * (1 + 5 * sum(math.exp(-0.5 * ((mm - k) / 9) ** 2) for k in keys)))
    def clock(u):                                                                # u 0→1 → 分钟
        x = u * cw[-1]; j = max(1, min(2000, next((k for k, v in enumerate(cw) if v >= x), 2000)))
        return lerp(grid[j - 1], grid[j], (x - cw[j - 1]) / max(1e-9, cw[j] - cw[j - 1]))
    def unclock(m): j = max(0, min(2000, round((m - m0) / (m1 - m0) * 2000))); return cw[j] / cw[-1]

    T0, T1 = D_DIVE + 0.8, D_DIVE + 0.8 + D_LAPSE; T_END = T1 + D_END + SPEC.get("tail", 0.4)
    N = int(round(T_END * fps)) + 1; cams, series = [], []
    for i in range(N):
        t = i / fps
        if t < D_DIVE: cam = geo.dive(t / D_DIVE, view, SPEC.get("spin", -70))
        elif t < T1:
            u = (t - D_DIVE) / (T1 - D_DIVE); cam = {**view, "z": z + 0.3 * smooth(u), "b": b_view + 8 * inout(u)}
        else:
            u = smooth((t - T1) / (D_END * 0.75)); cam = geo.blend({**view, "z": z + 0.3, "b": b_view + 8}, fin, u)
        m = clock(min(1, max(0, (t - T0) / D_LAPSE)))
        az, al = pos(m); s_spot = lit(hz_spot, spot)(m) if spot else 0
        series.append([round(az, 2), round(al, 2), round(m, 2), round(lit(hz_peak, peak)(m), 2), round(s_spot, 2)])
        cams.append(geo.frame(cam))

    t_of = lambda m: T0 + unclock(m) * D_LAPSE
    marks = [{"name": f"{pname}", "sub": "", "at": peak, "ele": round(pele)}] + ([{"name": f"{sname}（机位）", "sub": "", "at": spot, "ele": None}] if spot else [])
    marks += [{"name": m["name"], "sub": "", "at": geo.resolve(m), "ele": None} for m in SPEC.get("marks", [])]
    tl = {"runtime": "terrain", "width": W, "height": H, "fps": fps, "duration": round(T_END, 3),
          "title": SPEC.get("title", f"{pname} {'日照金山' if rise else '日落'}"), "sub": SPEC.get("sub", f"{day.month} 月 {day.day} 日 · 光线推演"),
          "exaggeration": SPEC.get("exaggeration", 1.35), "color": SPEC.get("color", "#ffc24a"), "hud": False,
          "phase": {"dive": D_DIVE, "ov": D_DIVE, "f0": 1e9, "f1": 1e9, "end": round(T_END, 3), "l0": T0, "l1": T1},
          "track": [[peak[0], peak[1], round(pele), 0, 0], [peak[0], peak[1], round(pele), 0.001, 0]],
          "stats": {"km": 0.001, "gain": 0, "loss": 0, "max": round(pele), "min": round(pele)},
          "sun": {"rise": rise, "date": f"{day.year}.{day.month:02d}.{day.day:02d}", "peak": peak, "spot": spot, "series": series,
                  "events": [{"name": n, "time": sun.hhmm(m) if m is not None else "—", "note": note, "t": round(t_of(m), 2) if m is not None and m0 <= m <= m1 else None} for n, m, note in ev]},
          "marks": marks, "layers": [], "frames": cams, "sfx": [], "attribution": ATTR + " · 太阳位置 NOAA 算法",
          "checks": [round(x, 2) for x in sorted((D_DIVE - 0.2, T0 + 1.0, min(T1 - 0.2, max(T0 + 0.6, t_of(t_peak) + 0.6)), T0 + D_LAPSE * 0.85, T_END - 0.1))]}
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(tl, ensure_ascii=False))
    print(f"timeline -> {out}  {tl['duration']}s  {W}×{H}  光线推演  {N} 帧")
