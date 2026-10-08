"""找机位的辅助命令（渲染本身交给 map-motion 的 make.sh）。

uv run --with certifi --with pillow --with pillow-heif python spot.py <命令> ...

  exif  照片.jpg|.heic           读 GPS（WGS-84）、拍摄时间、机型、等效焦距/光圈/快门/ISO，并给出 spec 可直接用的字段
  find  关键字 [--city 城市]     高德 POI 搜索，列候选（名称、GCJ-02 坐标、类型）；景点/山峰用这个，地理编码常查不到
  sheet 静帧目录 [-o 拼图.png]   把 --stills 抽出的帧横向拼成一张，一次 Read 看完
  ahead 经度,纬度 方位角 公里     从机位沿拍摄朝向走 N 公里的点（没有明确被摄地、只有 EXIF 朝向时，用它当 target 画取景扇形）
  gif   成片.mp4 [-o x.gif]      360px / 12fps 的预览 GIF（比 render.py 自带的小一半）
"""
import argparse, json, math, subprocess, sys
from pathlib import Path

MM = Path.home() / ".claude/skills/map-motion/scripts"          # 安装后的 map-motion
if not MM.exists(): MM = Path(__file__).resolve().parents[2] / "scripts"   # 仓库里直接跑
sys.path.insert(0, str(MM))


def cmd_exif(a):
    from PIL import Image
    try:
        import pillow_heif; pillow_heif.register_heif_opener()
    except ImportError:
        pass
    im = Image.open(a.photo); ex = im.getexif()
    base = dict(ex); sub = ex.get_ifd(0x8769); gps = ex.get_ifd(0x8825)
    def dms(v, ref):
        d, m, s = (float(x) for x in v); x = d + m / 60 + s / 3600
        return -x if ref in ("S", "W") else x
    out = {"size": list(im.size)}
    if gps.get(2) and gps.get(4):
        out["wgs84"] = [round(dms(gps[4], gps.get(3, "E")), 6), round(dms(gps[2], gps.get(1, "N")), 6)]
        if gps.get(17) is not None: out["direction"] = round(float(gps[17]), 1)          # 拍摄朝向（真北为 0，顺时针）——iPhone 一般都有
        if gps.get(6) is not None: out["altitude"] = round(float(gps[6]), 1)
    if sub.get(36867) or base.get(306): out["time"] = str(sub.get(36867) or base.get(306))
    if base.get(272): out["model"] = str(base[272]).strip("\x00 ")
    f35, fn, et, iso = sub.get(41989), sub.get(33437), sub.get(33434), sub.get(34855)
    if f35: out["focal35"] = int(f35); out["fov"] = round(math.degrees(2 * math.atan(36 / (2 * f35))), 1)   # 横向视角，给 spec 的 fov
    bits = []
    if iso: bits.append(f"ISO {iso}")
    if et: et = float(et); bits.append(f"1/{round(1 / et)}" if et < 1 else f"{et:g}s")
    if fn: bits.append(f"f/{float(fn):g}")
    if f35: bits.append(f"{f35}mm")
    if bits: out["exif"] = "   ".join(bits)
    if "time" in out: out["date"] = out["time"][:10].replace(":", ".")
    if "wgs84" not in out: out["note"] = "没有 GPS：聊天里粘贴/截图/微信传过的图会被去掉，要原图（照片 App「导出未修改的原件」）"
    print(json.dumps(out, ensure_ascii=False, indent=1))


def cmd_find(a):
    import amap
    d = amap.get("/v3/place/text", keywords=a.keyword, city=a.city or "", offset=a.n)
    pois = d.get("pois") or []
    if not pois: print("没有结果：换个叫法（繁简、加「峰/山/村/观景台」），或直接写坐标"); return
    for p in pois[: a.n]:
        print(f"{p['name']:<24} [{p['location']}]  {p.get('pname', '')}{p.get('cityname', '')}{p.get('adname', '')}  {p.get('type', '')}")


def cmd_sheet(a):
    fs = sorted(Path(a.dir).glob("*.png"))
    if not fs: raise SystemExit("目录里没有 png")
    w = max(200, min(400, 2400 // len(fs)))
    ins = sum((["-i", str(f)] for f in fs), [])
    fc = "".join(f"[{i}]scale={w}:-1[v{i}];" for i in range(len(fs))) + "".join(f"[v{i}]" for i in range(len(fs))) + f"hstack={len(fs)}" if len(fs) > 1 else f"[0]scale={w}:-1"
    out = a.o or str(Path(a.dir).with_suffix("")) + "-sheet.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, out], check=True); print(out)


def cmd_ahead(a):
    lng, lat = (float(x) for x in a.at.split(",")); b, d = math.radians(a.bearing), a.km / 6371
    la1, lo1 = math.radians(lat), math.radians(lng)
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(b))
    lo2 = lo1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2))
    print(f"[{math.degrees(lo2):.6f}, {math.degrees(la2):.6f}]")


def cmd_gif(a):
    out = a.o or str(Path(a.video).with_suffix(".gif"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf",
                    "fps=12,scale=360:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4", out], check=True)
    print(out)


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sp = ap.add_subparsers(dest="cmd", required=True)
p = sp.add_parser("exif"); p.add_argument("photo"); p.set_defaults(fn=cmd_exif)
p = sp.add_parser("find"); p.add_argument("keyword"); p.add_argument("--city"); p.add_argument("-n", type=int, default=6); p.set_defaults(fn=cmd_find)
p = sp.add_parser("sheet"); p.add_argument("dir"); p.add_argument("-o"); p.set_defaults(fn=cmd_sheet)
p = sp.add_parser("ahead"); p.add_argument("at"); p.add_argument("bearing", type=float); p.add_argument("km", type=float); p.set_defaults(fn=cmd_ahead)
p = sp.add_parser("gif"); p.add_argument("video"); p.add_argument("-o"); p.set_defaults(fn=cmd_gif)
a = ap.parse_args(); a.fn(a)
