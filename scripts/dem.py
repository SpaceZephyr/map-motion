"""地形高程：AWS Terrain Tiles（Terrarium 编码 PNG，全球 SRTM/ETOPO 融合，免 key）。
和 3D 渲染用的是同一套瓦片、同一个缓存（~/.cache/map-motion/tiles/dem/），轨迹海拔和画面里的山对得上。
坐标 WGS-84。需要 pillow。

命令行自查：uv run --with certifi --with pillow python dem.py 98.7549 28.3671
"""
import io, math, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import amap

URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
CACHE = Path.home() / ".cache/map-motion/tiles/dem"
Z = 13
_tiles = {}


def _tile(x, y, z=Z):
    k = (z, x, y)
    if k in _tiles: return _tiles[k]
    f = CACHE / str(z) / str(x) / f"{y}.img"
    if not f.exists():
        for i in range(3):
            try:
                data = urllib.request.urlopen(URL.format(z=z, x=x, y=y), timeout=30, context=amap._ctx()).read(); break
            except Exception as e:
                err = e; time.sleep(1 + i)
        else:
            raise SystemExit(f"高程瓦片下载失败：{err}")
        f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(data)
    from PIL import Image
    im = Image.open(io.BytesIO(f.read_bytes())).convert("RGB"); px = im.load(); n = im.size[0]
    _tiles[k] = (px, n); return _tiles[k]


def at(lng, lat, z=Z):
    """双线性插值的海拔（米）"""
    s = math.sin(math.radians(lat)); wx = (lng + 180) / 360 * 2 ** z; wy = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * 2 ** z
    def h(gx, gy):                                     # 全局像素 → 高程
        tx, ty = int(gx // 256), int(gy // 256); px, n = _tile(tx, ty, z); r, g, b = px[int(gx % 256), int(gy % 256)]
        return r * 256 + g + b / 256 - 32768
    gx, gy = wx * 256 - 0.5, wy * 256 - 0.5; x0, y0 = math.floor(gx), math.floor(gy); fx, fy = gx - x0, gy - y0
    return (h(x0, y0) * (1 - fx) + h(x0 + 1, y0) * fx) * (1 - fy) + (h(x0, y0 + 1) * (1 - fx) + h(x0 + 1, y0 + 1) * fx) * fy


if __name__ == "__main__":
    print(round(at(float(sys.argv[1]), float(sys.argv[2]))), "m")
