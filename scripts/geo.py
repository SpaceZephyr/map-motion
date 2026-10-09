"""公共几何与镜头件：各个 3D 片型（terrain3d 路线/单点、sunlight 光线……）共用，新片型直接 import。
坐标一律 WGS-84 [lng, lat]；相机帧格式 [lng, lat, zoom, pitch, bearing, 已走 km]（t3d.js 认这个）。
"""
import math

R_EARTH = 6371.0


def hav(a, b):
    """两点球面距离（km）"""
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    return 2 * R_EARTH * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2))


def bearing(a, b):
    """a 看向 b 的方位角（正北 0°，顺时针）"""
    la1, la2, dl = math.radians(a[1]), math.radians(b[1]), math.radians(b[0] - a[0])
    return math.degrees(math.atan2(math.sin(dl) * math.cos(la2), math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dl))) % 360


def dest(a, brg, km):
    """从 a 沿方位 brg 走 km 公里到的点"""
    d, b, la1, lo1 = km / R_EARTH, math.radians(brg), math.radians(a[1]), math.radians(a[0])
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2))
    return [math.degrees(lo2), math.degrees(la2)]


def merc(ll):
    s = math.sin(math.radians(max(-85, min(85, ll[1]))))
    return [(ll[0] + 180) / 360, 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)]


def unmerc(m):
    return [m[0] * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * m[1]))))]


def smooth(p): p = max(0.0, min(1.0, p)); return p * p * p * (p * (6 * p - 15) + 10)
def inout(p): p = max(0.0, min(1.0, p)); return -(math.cos(math.pi * p) - 1) / 2
def lerp(a, b, e): return a + (b - a) * e
def lerp_ang(a, b, e): return a + ((b - a + 540) % 360 - 180) * e


def fit_cam(pts, b, pitch, W, H, fw=0.8, fh=0.55, zmax=22):
    """朝向 b、俯角 pitch 时，把 pts 装进画面 fw×fh 的相机 {c, z, p, b}"""
    ms = [merc(p) for p in pts]; cx = sum(m[0] for m in ms) / len(ms); cy = sum(m[1] for m in ms) / len(ms)
    rb = math.radians(b); xs, ys = [], []
    for m in ms:
        dx, dy = m[0] - cx, m[1] - cy
        xs.append(dx * math.cos(rb) + dy * math.sin(rb)); ys.append(-dx * math.sin(rb) + dy * math.cos(rb))
    bw, bh = (max(xs) - min(xs)) or 1e-6, ((max(ys) - min(ys)) or 1e-6) * math.cos(math.radians(pitch)) * 1.15
    z = math.log2(min(W * fw / (bw * 512), H * fh / (bh * 512)))
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2                    # 旋转框中心换回墨卡托
    c = unmerc([cx + mx * math.cos(rb) - my * math.sin(rb), cy + mx * math.sin(rb) + my * math.cos(rb)])
    return {"c": c, "z": min(z, zmax), "p": pitch, "b": b % 360}


def dive(u, to, spin=-70):
    """地球俯冲（u: 0→1）：从 1.4 级的地球转着落到相机 to = {c, z, p, b}"""
    e = inout(u); ce = smooth(u / 0.85); ll = to["c"]
    return {"c": [ll[0] + spin * (1 - ce), lerp(ll[1] * 0.4, ll[1], ce)], "z": lerp(1.4, to["z"], e ** 1.15),
            "p": lerp(0, to["p"], smooth((u - 0.55) / 0.45)), "b": lerp_ang(0, to["b"], smooth((u - 0.5) / 0.5))}


def blend(a, b, u, zu=None):
    """两个相机之间过渡（u 已缓动）；zu 单独给缩放的进度"""
    zu = u if zu is None else zu
    return {"c": [lerp(a["c"][0], b["c"][0], u), lerp(a["c"][1], b["c"][1], u)], "z": lerp(a["z"], b["z"], zu),
            "p": lerp(a["p"], b["p"], u), "b": lerp_ang(a["b"], b["b"], u)}


def frame(cam, km=0):
    """相机 → 时间轴帧 [lng, lat, zoom, pitch, bearing, km]"""
    return [round(cam["c"][0], 6), round(cam["c"][1], 6), round(cam["z"], 4), round(cam["p"], 2), round(cam["b"] % 360, 2), round(km, 4)]


ATTR = "Imagery © Esri, Maxar, Earthstar Geographics · Terrain © Mapzen, AWS"


def resolve(p, gcj=False, log=True):
    """[lng,lat]（WGS；gcj=True 时按高德坐标）| "地名" | {"name","at"} → WGS [lng,lat]。地名经高德解析并打印，供核对"""
    import amap, elev
    if isinstance(p, dict): p = p.get("at") or p.get("name")
    if isinstance(p, str):
        g = amap.geocode(p)
        if log: print(f"     地点 {p} → {g['name']}（{g['level']}）")
        return elev.gcj2wgs(*g["lnglat"])
    return elev.gcj2wgs(*p) if gcj else list(p)
