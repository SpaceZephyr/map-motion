"""沿路线取海拔剖面：OpenTopoData SRTM 30m（免费，每次 100 点、约 1 次/秒）。
输入 GCJ-02 折线（高德），先换回 WGS-84 再查——山里差几百米海拔就差很多。结果缓存在 ~/.cache/map-motion/elev/。

命令行自查：uv run --with certifi python elev.py 114.2194 22.5795
"""
import hashlib, json, math, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import amap

CACHE = Path.home() / ".cache/map-motion/elev"
API = "https://api.opentopodata.org/v1/srtm30m?locations="


def gcj2wgs(lng, lat):
    """GCJ-02 → WGS-84（两次迭代，误差 < 1 m）"""
    w = [lng, lat]
    for _ in range(2):
        g = amap.wgs2gcj(*w); w = [w[0] - (g[0] - lng), w[1] - (g[1] - lat)]
    return w


def lookup(pts_wgs):
    out = []
    for i in range(0, len(pts_wgs), 100):
        batch = pts_wgs[i:i + 100]; q = "|".join(f"{p[1]:.6f},{p[0]:.6f}" for p in batch)
        f = CACHE / (hashlib.md5(q.encode()).hexdigest() + ".json")
        if f.exists(): out += json.loads(f.read_text()); continue
        for k in range(4):
            try:
                time.sleep(1.1)
                d = json.load(urllib.request.urlopen(API + q, timeout=40, context=amap._ctx()))
                if d.get("status") == "OK": break
            except Exception as e:
                d = {"error": str(e)}; time.sleep(2 * (k + 1))
        else:
            raise SystemExit(f"海拔查询失败：{d.get('error')}（OpenTopoData 免费额度每天 1000 次）")
        es = [r["elevation"] if r["elevation"] is not None else 0 for r in d["results"]]
        CACHE.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(es)); out += es
    return out


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    return 6371 * 2 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))


def profile(line, n=120):
    """沿 GCJ 折线按距离均匀取 n 个点 → {samples: [[km, m], …], gain, loss, max, min, km}"""
    cum = [0.0]
    for i in range(1, len(line)): cum.append(cum[-1] + hav(line[i - 1], line[i]))
    L = cum[-1]; pts = []; j = 1
    for k in range(n):
        d = L * k / (n - 1)
        while j < len(cum) - 1 and cum[j] < d: j += 1
        f = (d - cum[j - 1]) / max(1e-12, cum[j] - cum[j - 1]); a, b = line[j - 1], line[j]
        pts.append([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f])
    es = lookup([gcj2wgs(*p) for p in pts])
    sm = [sum(es[max(0, i - 1):i + 2]) / len(es[max(0, i - 1):i + 2]) for i in range(len(es))]   # 轻微平滑，去 SRTM 噪点
    gain = sum(max(0, sm[i] - sm[i - 1]) for i in range(1, len(sm))); loss = sum(max(0, sm[i - 1] - sm[i]) for i in range(1, len(sm)))
    return {"samples": [[round(L * k / (n - 1), 3), round(e)] for k, e in enumerate(sm)], "gain": round(gain), "loss": round(loss),
            "max": round(max(sm)), "min": round(min(sm)), "km": round(L, 2)}


def at(lng, lat):
    return round(lookup([gcj2wgs(lng, lat)])[0])


if __name__ == "__main__":
    print(at(float(sys.argv[1]), float(sys.argv[2])), "m")
