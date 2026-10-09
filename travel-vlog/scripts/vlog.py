"""旅行 vlog 的辅助命令（编译和渲染交给 map-motion 引擎：scripts/compile.py、render.py）。

  avatar  [--photo 人像.jpg] [--describe 文字] [-o avatar/]   生成卡通形象：走路 + 拍照两个姿势，抠成白边贴纸（LabNana 图像接口）
  plan    照片… [-o vlog.json] [--mode walking|driving] [--title 标题]
                                 读每张照片的 GPS 和拍摄时间 → 按时间排序、近的合成一个机位 → 高德取地名 → 写好 spec
  check   vlog.json              编译 + 每个机位「咔嚓」后、片尾照片墙各抽一帧，自动质检，出拼图
  make    vlog.json 成片.mp4      整片（带 BGM 和音效）+ 预览 GIF
  status                         渲染进度
"""
import argparse, base64, io, json, math, os, shutil, subprocess, sys, urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENG = HERE.parents[1] / "scripts"
if not (ENG / "compile.py").exists(): ENG = Path.home() / ".claude/skills/map-motion/scripts"
sys.path.insert(0, str(ENG))
UV = ["uv", "run", "-q", "--with", "certifi", "--with", "pillow", "--with", "playwright", "python"]


# ---------------- 卡通形象
STYLE = ("Q 版（2.5 头身）全身卡通形象，扁平插画风，干净的深色描边，明亮温暖的配色，表情开心；"
         "人物完整不裁切，四周留足白边；纯白背景（#FFFFFF），不要地面、不要阴影、不要任何文字和边框。")
WALK = "侧身朝向画面右边、正在迈步走路，背一个小双肩包，一只手自然摆动。"
SNAP = "同一个角色、同样的发型衣服和背包，侧身朝向画面右边，双手举着一台相机贴在眼前正在拍照。"


def labnana_key():
    k = os.environ.get("LABNANA_API_KEY")
    if k: return k, os.environ.get("LABNANA_API_URL", "https://api.labnana.com")
    for f in [HERE.parent / ".labnana.env", Path.home() / ".claude/skills/person-image-studio/.labnana.env"]:
        if f.exists():
            kv = dict(l.strip().split("=", 1) for l in f.read_text().splitlines() if "=" in l and not l.startswith("#"))
            if kv.get("LABNANA_API_KEY"): return kv["LABNANA_API_KEY"], kv.get("LABNANA_API_URL", "https://api.labnana.com")
    raise SystemExit("没有 LabNana key：设环境变量 LABNANA_API_KEY，或在 travel-vlog/.labnana.env 写 LABNANA_API_KEY=…")


def gen_image(prompt, refs, out, model):
    key, url = labnana_key()
    prov = {"gpt-image-2": "openai", "gemini-3-pro-image": "google", "gemini-3.1-flash-image": "google"}.get(model, "openai")
    body = {"provider": prov, "model": model, "prompt": prompt, "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"},
            "referenceImages": [{"inlineData": {"data": base64.b64encode(r).decode(), "mimeType": "image/jpeg"}} for r in refs]}
    req = urllib.request.Request(f"{url}/openapi/v1/images/generation", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    import ssl
    try:
        import certifi; ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        res = json.loads(urllib.request.urlopen(req, timeout=300, context=ctx).read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"图像接口报错 {e.code}：{e.read()[:300].decode(errors='replace')}")
    for part in (res.get("candidates") or [{}])[0].get("content", {}).get("parts", []):
        if part.get("inlineData", {}).get("data") and not part.get("thought"):
            Path(out).write_bytes(base64.b64decode(part["inlineData"]["data"])); return out
    raise SystemExit("图像接口没返回图片：" + json.dumps(res, ensure_ascii=False)[:300])


def jpeg(path, side=1024):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB"); im.thumbnail((side, side))
    b = io.BytesIO(); im.save(b, "JPEG", quality=90); return b.getvalue()


def sticker(src, dst, h=640):
    """白底卡通图 → 透明贴纸：从四边漫填掉近白背景，留主体，外面加一圈白边和淡投影（抠图毛边被白边盖住）"""
    from PIL import Image, ImageDraw, ImageFilter, ImageChops
    im = Image.open(src).convert("RGB"); w, hh = im.size
    px = im.load(); bg = Image.new("L", im.size, 0); seen = bytearray(w * hh); stack = []
    near = lambda p: min(p) > 228 and max(p) - min(p) < 22
    for x in range(w): stack += [(x, 0), (x, hh - 1)]
    for y in range(hh): stack += [(0, y), (w - 1, y)]
    bp = bg.load()
    while stack:
        x, y = stack.pop(); i = y * w + x
        if seen[i]: continue
        seen[i] = 1
        if not near(px[x, y]): continue
        bp[x, y] = 255
        if x > 0: stack.append((x - 1, y))
        if x < w - 1: stack.append((x + 1, y))
        if y > 0: stack.append((x, y - 1))
        if y < hh - 1: stack.append((x, y + 1))
    alpha = ImageChops.invert(bg).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))          # 去掉零星噪点
    rim = alpha.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(1.2))                     # 白边
    shadow = rim.filter(ImageFilter.GaussianBlur(6)).point(lambda v: v * 0.35)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste((60, 40, 20, 255), (0, 0), ImageChops.offset(shadow, 0, 5)); out.paste((255, 255, 255, 255), (0, 0), rim)
    body = im.convert("RGBA"); body.putalpha(alpha); out.alpha_composite(body)
    bb = out.getbbox(); out = out.crop((max(0, bb[0] - 6), max(0, bb[1] - 6), min(w, bb[2] + 6), min(hh, bb[3] + 6)))
    out = out.resize((round(out.width * h / out.height), h), Image.LANCZOS); out.save(dst); return out.size


def builtin(path, pose, hair="#3b2a20", top="#ffcc33", pants="#6f9fd8", bag="#ff7a45", skin="#f8d6bd"):
    """内置 Q 版小人（不调任何服务）：朝右，走路或举相机；画在白底上，再走 sticker() 抠成贴纸"""
    from PIL import Image, ImageDraw
    S = 4; im = Image.new("RGB", (300 * S, 420 * S), "white"); g = ImageDraw.Draw(im); O = "#3a2a18"; lw = 6 * S
    def el(b, f): g.ellipse([v * S for v in b], fill=f, outline=O, width=lw)
    def rr(b, f, r=18): g.rounded_rectangle([v * S for v in b], r * S, fill=f, outline=O, width=lw)
    def ln(pts, w, f): g.line([(x * S, y * S) for x, y in pts], fill=O, width=(w + 12) * S, joint="curve"); g.line([(x * S, y * S) for x, y in pts], fill=f, width=w * S, joint="curve")
    rr((70, 205, 128, 300), bag, 20)                                              # 背包（在背后＝左边）
    ln([(140, 330), (118, 385)], 26, pants); ln([(168, 330), (196, 382)], 26, pants)      # 迈步的两条腿
    el((92, 372, 136, 398), "#ffffff"); el((180, 368, 226, 394), "#ffffff")              # 鞋
    rr((106, 220, 202, 340), top, 30)                                             # 卫衣
    if pose == "snap":
        ln([(176, 248), (214, 178)], 22, top); ln([(146, 250), (200, 186)], 22, top)
        rr((188, 104, 262, 160), "#41464f", 10); el((216, 112, 252, 150), "#9fc4e8"); rr((196, 94, 218, 106), "#41464f", 3)    # 相机贴在眼前
    else:
        ln([(130, 245), (112, 300)], 22, top); ln([(180, 245), (206, 296)], 22, top)
    el((70, 40, 236, 206), skin)                                                  # 大头
    g.chord([70 * S, 32 * S, 240 * S, 196 * S], 180, 360, fill=hair, outline=O, width=lw)
    g.polygon([(x * S, y * S) for x, y in [(70, 120), (96, 70), (120, 118)]], fill=hair)   # 侧边头发
    if pose != "snap":
        el((176, 118, 192, 138), O); g.ellipse([(178 * S, 120 * S), (184 * S, 126 * S)], fill="white")   # 眼睛
        g.arc([(176 * S, 140 * S), (214 * S, 168 * S)], 20, 120, fill=O, width=lw)                       # 笑
    el((196, 142, 222, 156), "#ffb3a7"); g.ellipse([(196 * S, 142 * S), (222 * S, 156 * S)], fill="#ffb3a7")
    im.resize((300, 420), Image.LANCZOS).save(path)


def cmd_avatar(a):
    d = Path(a.o); d.mkdir(parents=True, exist_ok=True)
    if a.builtin is not None:
        kw = dict(x.split("=", 1) for x in a.builtin.split(",") if "=" in x)
        for k in ("walk", "snap"): builtin(d / f"{k}_raw.png", k, **kw); print(f"  {k}.png", sticker(d / f"{k}_raw.png", d / f"{k}.png"))
        print(f"✓ 内置形象 → {d}"); return
    if not a.photo and not a.describe: raise SystemExit("给 --photo 人像照片，或 --describe 文字描述，或 --builtin")
    refs = [jpeg(a.photo)] if a.photo else []
    who = ("参考照片里的这个人：保留发型、发色、脸型、眼镜/配饰等特征和衣服颜色。" if a.photo else "") + (a.describe or "")
    print(f"生成走路姿势（{a.model}）…", flush=True)
    gen_image(f"画一个{who}{STYLE}{WALK}", refs, d / "walk_raw.png", a.model)
    print("生成拍照姿势（参考走路那张，保持同一角色）…", flush=True)
    gen_image(f"画{who}{STYLE}{SNAP}", refs + [jpeg(d / "walk_raw.png")], d / "snap_raw.png", a.model)
    for k in ("walk", "snap"): print(f"  {k}.png", sticker(d / f"{k}_raw.png", d / f"{k}.png"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(d / "walk.png"), "-i", str(d / "snap.png"), "-filter_complex",
                    "[0]scale=-2:400[a];[1]scale=-2:400[b];[a][b]hstack=2,format=rgba[s];color=c=#e9dcc2:s=1600x400[bg];[bg][s]overlay=(W-w)/2:0:shortest=1",
                    "-frames:v", "1", str(d / "preview.png")], check=True)
    print(f"✓ 形象 → {d}/walk.png、snap.png（预览 {d}/preview.png）")


# ---------------- 照片 → 机位
def exif(path):
    from PIL import Image
    try:
        import pillow_heif; pillow_heif.register_heif_opener()
    except ImportError:
        pass
    im = Image.open(path); ex = im.getexif(); gps = ex.get_ifd(0x8825); sub = ex.get_ifd(0x8769)
    dms = lambda v, ref: (-1 if ref in ("S", "W") else 1) * sum(float(x) / 60 ** i for i, x in enumerate(v))
    out = {"file": str(path)}
    if gps.get(2) and gps.get(4): out["wgs84"] = [round(dms(gps[4], gps.get(3, "E")), 6), round(dms(gps[2], gps.get(1, "N")), 6)]
    ts = sub.get(36867) or ex.get(306)
    if ts:
        try: out["time"] = datetime.strptime(str(ts).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
        except ValueError: pass
    return out


def hav(a, b):
    la1, la2 = math.radians(a[1]), math.radians(b[1])
    return 2 * 6371 * math.asin(math.sqrt(math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2))


def place_name(wgs):
    import amap
    g = amap.wgs2gcj(*wgs)
    r = amap.get("/v3/geocode/regeo", location=f"{g[0]:.6f},{g[1]:.6f}", extensions="all", radius=300).get("regeocode", {})
    for k, lim in (("pois", 150), ("aois", 300)):                    # 先找最近的景点/店名，再退到所在的大片区域
        for x in sorted(r.get(k) or [], key=lambda x: float(x.get("distance", 0) or 0)):
            if x.get("name") and float(x.get("distance", 0) or 0) < lim: return x["name"].split("-")[-1]
    ac = r.get("addressComponent", {}); return (ac.get("township") or ac.get("district") or "某处") if isinstance(ac.get("township"), str) else "某处"


def cmd_plan(a):
    from PIL import Image, ImageOps
    out = Path(a.o).resolve(); proj = out.parent; (proj / "photos").mkdir(parents=True, exist_ok=True)
    infos, miss = [], []
    for p in a.photos:
        e = exif(p); (infos if "wgs84" in e else miss).append(e)
    if miss: print("⚠ 这些照片没有 GPS（聊天里粘贴/截图/微信传过的会被去掉；要原图）：\n  " + "\n  ".join(Path(m["file"]).name for m in miss))
    if not infos: raise SystemExit("没有一张带 GPS 的照片：请给原图，或在 spec 里手写每个机位的地名")
    infos.sort(key=lambda e: e.get("time") or datetime.min)
    stops = []
    for e in infos:                                                   # 和上一个机位相距 < merge 米：算同一个机位（最多 2 张）
        if stops and hav(stops[-1]["at"], e["wgs84"]) * 1000 < a.merge and len(stops[-1]["photos"]) < 2: stops[-1]["photos"].append(e)
        else: stops.append({"at": e["wgs84"], "photos": [e]})
    names = {}
    for i, s in enumerate(stops):
        n = place_name(s["at"]); n = n if n not in names else f"{n}·{i + 1}"; names[n] = 1; s["name"] = n
        for k, e in enumerate(s["photos"]):                           # 照片统一转 JPG、长边 1600（HEIC 也能用，渲染更快）
            f = proj / "photos" / f"{i + 1:02d}_{k + 1}.jpg"; im = ImageOps.exif_transpose(Image.open(e["file"])).convert("RGB"); im.thumbnail((1600, 1600)); im.save(f, quality=88)
            e["rel"] = str(f.relative_to(proj))
        t = s["photos"][0].get("time"); print(f"  {i + 1}. {n:<16} {s['at']}  {t.strftime('%m-%d %H:%M') if t else ''}  照片 {len(s['photos'])} 张")
    total = sum(hav(x["at"], y["at"]) for x, y in zip(stops, stops[1:]))
    mode = a.mode or ("walking" if total < 12 else "driving")
    t0 = stops[0]["photos"][0].get("time")
    spec = {"size": "portrait", "style": a.style, "tail": 0.4, "music": {"bpm": a.bpm, "seed": a.seed},
            "shots": [
                {"type": "globe", "to": {"name": stops[0]["name"], "at": stops[0]["at"], "wgs84": True}, "zoom": 14.5, "dur": 5.5,
                 "label": a.title or f"{stops[0]['name']} 出发", "sub": t0.strftime("%Y.%m.%d") if t0 else ""},
                {"type": "trip", "mode": mode, "stamp": False, "days": False, "overview": len(stops) > 2,
                 "title": {"text": a.title or "今天去哪了", "sub": f"{len(stops)} 个机位", "pos": "top"},
                 "stops": [{"name": s["name"], "at": s["at"], "wgs84": True} for s in stops],
                 "photos": {s["name"]: [{"image": e["rel"], "caption": s["name"]} for e in s["photos"]] for s in stops},
                 "avatar": {"walk": "avatar/walk.png", "snap": "avatar/snap.png"}},
                {"type": "wall", "sub": a.title or ""}]}
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=1))
    print(f"✓ {len(stops)} 个机位、直线合计 {total:.1f} km → {mode}；spec → {out}")
    if not (proj / "avatar/walk.png").exists(): print("  还没有形象：vlog.sh avatar --photo 人像.jpg -o " + str(proj / "avatar"))


# ---------------- 出片
def compile_(spec):
    tl = spec.with_name(spec.stem + ".timeline.json")
    r = subprocess.run(UV + [str(ENG / "compile.py"), str(spec), "--out", str(tl)], capture_output=True, text=True)
    for l in r.stdout.splitlines():
        if any(k in l for k in ("地点", "timeline", "⚠")): print(l.replace(str(tl.parent) + "/", ""))
    if r.returncode: print(r.stdout[-1500:], r.stderr[-1500:]); raise SystemExit("编译失败")
    return tl


def render(tl, *args):
    r = subprocess.run(UV + [str(ENG / "render.py"), str(tl), *args], capture_output=True, text=True)
    keep = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()]
    if r.returncode: print("\n".join(keep[-12:])); raise SystemExit("渲染失败")
    return keep


def cmd_check(a):
    spec = Path(a.spec).resolve(); tl = compile_(spec); T = json.loads(tl.read_text())
    ts = sorted({round(L["snap_t"] + 0.12, 2) for L in T["layers"] if L["type"] == "actor" and L.get("snap_t")} |
                {round(L["t0"] + 0.9, 2) for L in T["layers"] if L["type"] == "photo"} |
                {round(L["t0"] + (L["t1"] - L["t0"]) * 0.5, 2) for L in T["layers"] if L["type"] == "route" and L.get("vehicle") == "avatar"} | {round(T["duration"] - 0.2, 2)})
    d = spec.parent / (spec.stem + "-check"); shutil.rmtree(d, ignore_errors=True)
    for l in render(tl, "--stills", ",".join(map(str, ts)), "--out", str(d)):
        if l.startswith(("质检", "  ✗", "瓦片")): print(l)
    shots = sorted(d.glob("t*.png")); n = len(shots); cols = min(n, 6)
    sheet = str(spec.with_name(spec.stem + "-check.png"))
    ins = sum((["-i", str(s)] for s in shots), [])
    fc = "".join(f"[{i}]scale=270:-2[s{i}];" for i in range(n)) + "".join(f"[s{i}]" for i in range(n)) + f"xstack=inputs={n}:layout=" + "|".join(f"{(i % cols) * 270}_{(i // cols) * 480}" for i in range(n)) + ":fill=black"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc if n > 1 else "[0]scale=270:-2", sheet], check=True)
    print(f"抽查时刻 {', '.join(f'{t}s' for t in ts)}；拼图 {sheet}")


def cmd_make(a):
    spec = Path(a.spec).resolve(); tl = compile_(spec); out = Path(a.out).resolve()
    for l in render(tl, "--out", str(out)): print(l)
    g = out.with_suffix(".gif")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-vf", "fps=12,scale=320:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4", str(g)], check=True)
    print("gif ->", g)


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sp = ap.add_subparsers(dest="cmd", required=True)
p = sp.add_parser("avatar"); p.add_argument("--photo"); p.add_argument("--describe"); p.add_argument("-o", default="avatar"); p.add_argument("--model", default="gpt-image-2")
p.add_argument("--builtin", nargs="?", const="", help="内置小人，可换色：hair=#333,top=#ffcc33,pants=#6f9fd8,bag=#ff7a45"); p.set_defaults(fn=cmd_avatar)
p = sp.add_parser("plan"); p.add_argument("photos", nargs="+"); p.add_argument("-o", default="vlog.json"); p.add_argument("--mode", choices=["walking", "driving", "bicycling"])
p.add_argument("--title"); p.add_argument("--style", default="amap-journal"); p.add_argument("--merge", type=float, default=120); p.add_argument("--bpm", type=int, default=120); p.add_argument("--seed", type=int, default=1); p.set_defaults(fn=cmd_plan)
p = sp.add_parser("check"); p.add_argument("spec"); p.set_defaults(fn=cmd_check)
p = sp.add_parser("make"); p.add_argument("spec"); p.add_argument("out"); p.set_defaults(fn=cmd_make)
p = sp.add_parser("status"); p.add_argument("dirs", nargs="*"); p.set_defaults(fn=lambda a: subprocess.run(["python3", str(ENG / "status.py"), *a.dirs]))
a = ap.parse_args(); a.fn(a)
