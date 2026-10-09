"""timeline.json → MP4 / GIF / 静帧。起本地服务（运行时 + 内置底图 + 高德瓦片代理与缓存）→ 无头 Chromium 逐帧画 → ffmpeg。

uv run --with playwright --with certifi python render.py timeline.json --out 成片.mp4 [--gif 动图.gif] [--audio 配乐.wav]
uv run --with playwright --with certifi python render.py timeline.json --stills 0,2.5,6 --out 静帧目录/
首次用：uv run --with playwright playwright install chromium

瓦片缓存在 ~/.cache/map-motion/tiles/（同一片子重渲不再请求）。页面报错 → 非零退出。
"""
import argparse, base64, functools, http.server, json, socketserver, ssl, subprocess, threading, time, urllib.parse, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
import sys; sys.path.insert(0, str(Path(__file__).parent)); import qa, audio

HERE = Path(__file__).parent
ASSETS = HERE.parent / "assets"
TCACHE = Path.home() / ".cache/map-motion/tiles"
SRC = {   # 高德瓦片（GCJ-02 墨卡托）：amap＝标准路网 512px，sat＝卫星 256px，lbl＝卫星上的路名地名叠加 512px
    "amap": "https://wprd0{s}.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=2&style=7",
    "sat": "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
    "lbl": "https://wprd0{s}.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=2&style=8&ltype=4",
    "esri": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",   # 境外卫星（WGS-84 墨卡托，全球高清）；高德卫星境外只有城市级
    "dem": "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",   # 3D 地形：AWS Terrain Tiles（Terrarium 编码高程）
}
VENDOR = {"maplibre-gl.js": "https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js"}   # 3D 运行时用，首次下载后缓存
VCACHE = Path.home() / ".cache/map-motion/vendor"

ap = argparse.ArgumentParser()
ap.add_argument("timeline"); ap.add_argument("--out", required=True)
ap.add_argument("--stills"); ap.add_argument("--gif"); ap.add_argument("--audio")
ap.add_argument("--gif-width", type=int, default=480); ap.add_argument("--gif-fps", type=int, default=12)
ap.add_argument("--qa-every", type=float, default=0.5, help="整片渲染时每隔几秒抽一帧质检，0 关闭")
ap.add_argument("-v", "--verbose", action="store_true", help="打印逐段进度和页面日志（缺省只在结束时出一段摘要）")
ap.add_argument("--crf", type=int, default=20); ap.add_argument("--from", dest="t0", type=float, default=0); ap.add_argument("--to", dest="t1", type=float)
A = ap.parse_args()

tl_path = Path(A.timeline).resolve(); TL = json.loads(tl_path.read_text())
ALLOWED = {}
for L in TL["layers"]:                                   # 本地图片（照片）→ /file/<序号>，只服务点名的文件
    if L.get("image") and not L["image"].startswith(("http:", "https:", "data:")):
        f = (tl_path.parent / L["image"]).resolve()
        if not f.exists(): raise SystemExit(f"图片不存在：{L['image']}")
        k = str(len(ALLOWED)); ALLOWED[k] = f; L["image"] = f"/file/{k}{f.suffix}"
    if L.get("frames"):                                  # Live Photo 抽出的帧
        fl = []
        for fp in L["frames"]:
            f = (tl_path.parent / fp).resolve(); k = str(len(ALLOWED)); ALLOWED[k] = f; fl.append(f"/file/{k}{f.suffix}")
        L["frames"] = fl
    for ph in L.get("photos") or []:                    # 片尾照片墙
        if not ph["image"].startswith(("/file/", "http")):
            f = (tl_path.parent / ph["image"]).resolve()
            if not f.exists(): raise SystemExit(f"图片不存在：{ph['image']}")
            k = str(len(ALLOWED)); ALLOWED[k] = f; ph["image"] = f"/file/{k}{f.suffix}"
    if L.get("avatar"):                                  # 卡通形象贴纸（走路 / 拍照两个姿势）
        for k, fp in list(L["avatar"].items()):
            f = (tl_path.parent / fp).resolve()
            if not f.exists(): raise SystemExit(f"形象图不存在：{fp}")
            i = str(len(ALLOWED)); ALLOWED[i] = f; L["avatar"][k] = f"/file/{i}{f.suffix}"
MUSIC = TL.get("music")
if MUSIC and MUSIC.get("file"):
    MUSIC["file"] = str((tl_path.parent / MUSIC["file"]).resolve())

try:
    import certifi; CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = ssl.create_default_context()
LOCK = threading.Lock(); STATS = {"net": 0, "cache": 0, "fail": 0}


def tile(src, z, x, y):
    f = TCACHE / src / str(z) / str(x) / f"{y}.img"
    if f.exists(): STATS["cache"] += 1; return f.read_bytes()
    url = SRC[src].format(s=1 + (x + y) % 4, x=x, y=y, z=z)
    for k in range(3):
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.amap.com/"}), timeout=20, context=CTX).read()
            f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(data); STATS["net"] += 1; return data
        except Exception:
            time.sleep(0.5 * (k + 1))
    STATS["fail"] += 1; return None


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, data, ctype):
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        p = urllib.parse.unquote(self.path.split("?")[0])
        if p.startswith("/tile/"):
            _, _, src, z, x, y = p.split("/")
            d = tile(src, int(z), int(x), int(y))
            return self._send(d, "image/jpeg" if src in ("sat", "esri") else "image/png") if d else self.send_error(404)
        if p.startswith("/vendor/") and p[8:] in VENDOR:
            f = VCACHE / VENDOR[p[8:]].split("/")[3] / p[8:]
            if not f.exists():
                f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(urllib.request.urlopen(VENDOR[p[8:]], timeout=60, context=CTX).read())
            return self._send(f.read_bytes(), "text/javascript")
        if p.startswith("/asset/"):
            f = (ASSETS / p[len("/asset/"):]).resolve()
            if ASSETS in f.parents and f.exists(): return self._send(f.read_bytes(), "font/woff" if f.suffix == ".woff" else "application/json")
            return self.send_error(404)
        if p.startswith("/file/"):
            f = ALLOWED.get(Path(p).stem)
            return self._send(f.read_bytes(), "image/jpeg" if f.suffix.lower() in (".jpg", ".jpeg") else "image/png") if f else self.send_error(404)
        return super().do_GET()


class TS(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    def handle_error(self, *a): pass                          # 浏览器取消的瓦片请求（断管）不刷屏
srv = TS(("127.0.0.1", 0), functools.partial(Q, directory=str(HERE / "runtime")))
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]

errors = []
with sync_playwright() as pw:
    RT = TL.get("runtime", "index")                          # 运行时页面 runtime/<RT>.html；都实现 prepare(t) / renderFrame(t) / __canvas
    WEBGL = RT in ("terrain",) or TL.get("webgl")           # 3D 地形片：MapLibre（WebGL，无头下走 SwiftShader 软件渲染）
    b = pw.chromium.launch(args=["--disable-web-security"] + (["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] if WEBGL else []))
    pg = b.new_page(viewport={"width": TL["width"], "height": TL["height"]}, device_scale_factor=1)
    pg.on("console", lambda m: (A.verbose and print("[page]", m.text), errors.append(m.text)) if m.type == "error" else None)
    pg.on("pageerror", lambda e: (A.verbose and print("[pageerror]", e), errors.append(str(e))))
    pg.add_init_script("window.MM_TIMELINE = " + json.dumps(TL, ensure_ascii=False) + ";")
    pg.goto(f"http://127.0.0.1:{port}/{RT}.html")
    pg.wait_for_function("window.__ready === true || !!window.__bootFailed", timeout=120000)
    if pg.evaluate("window.__bootFailed || null"): raise SystemExit("运行时启动失败：\n" + pg.evaluate("window.__bootFailed"))
    grab = "async (t) => { await window.prepare(t); window.renderFrame(t); return window.__canvas.toDataURL('image/png').split(',')[1]; }"
    grabq = "async (t) => { await window.prepare(t); window.__qaBegin(); window.renderFrame(t); const q = window.__qaEnd(); return [window.__canvas.toDataURL('image/png').split(',')[1], q]; }"
    samples, W_, H_ = [], TL["width"], TL["height"]
    fps, t1 = TL["fps"], A.t1 if A.t1 is not None else TL["duration"]
    if A.stills:
        out = Path(A.out); out.mkdir(parents=True, exist_ok=True)
        for s in A.stills.split(","):
            png, q = pg.evaluate(grabq, float(s)); samples.append((float(s), q))
            (out / f"t{float(s):06.2f}.png").write_bytes(base64.b64decode(png))
        print(f"✓ 静帧 {len(samples)} 张 -> {out}")
        print(qa.report(samples, W_, H_, 1e9, out / "qa.json"))
    else:
        out = Path(A.out); out.parent.mkdir(parents=True, exist_ok=True)
        if not A.audio and (TL.get("sfx") or MUSIC):      # 没给 --audio：音效点（快门、脚步、啵、叮）＋ 时间轴里的配乐，合成一条音轨（audio.py）
            A.audio = str(out.with_suffix(".sfx.wav")); audio.mix(TL.get("sfx", []), TL["duration"], A.audio, MUSIC)
        vid = out.with_suffix(".noaudio.mp4") if A.audio else out
        ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
                               "-c:v", "libx264", "-preset", "slow", "-crf", str(A.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(vid)], stdin=subprocess.PIPE)
        n0, n1, st = round(A.t0 * fps), round(t1 * fps), time.time()
        every = max(1, round(A.qa_every * fps)) if A.qa_every > 0 else 0
        prog = out.with_name(out.name + ".progress")              # 给 status.py 看的进度（一行 JSON）
        for i in range(n0, n1):
            if every and ((i - n0) % every == 0 or i == n1 - 1):
                png, q = pg.evaluate(grabq, i / fps); samples.append((i / fps, q))
            else:
                png = pg.evaluate(grab, i / fps)
            ff.stdin.write(base64.b64decode(png))
            if (i - n0) % fps == 0 or i == n1 - 1:
                k, el = i - n0 + 1, time.time() - st
                prog.write_text(json.dumps({"out": str(out), "done": k, "total": n1 - n0, "elapsed": round(el), "eta": round(el / k * (n1 - n0 - k)), "t": time.time()}))
                if A.verbose and (i - n0) % (fps * 5) == 0: print(f"  {i}/{n1} 帧  {el:.0f}s", flush=True)
        ff.stdin.close(); ff.wait()
        if A.audio:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-ss", str(A.t0), "-i", A.audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True); vid.unlink()
        if A.audio and A.audio.endswith(".sfx.wav"): Path(A.audio).unlink(missing_ok=True)
        prog.unlink(missing_ok=True)
        print(f"✓ 成片 {out}（{(n1 - n0) / fps:.1f}s，{n1 - n0} 帧，用时 {(time.time() - st) / 60:.1f} 分钟）")
        if every: print(qa.report(samples, W_, H_, every / fps, out.with_suffix(".qa.json")))
        if A.gif:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-vf",
                            f"fps={A.gif_fps},scale={A.gif_width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", A.gif], check=True)
            print(f"✓ GIF {A.gif}")
    b.close()
srv.shutdown()
if A.verbose or STATS["fail"]: print(f"瓦片：新取 {STATS['net']}，缓存 {STATS['cache']}，失败 {STATS['fail']}" + ("（失败的地方会是空白/灰块）" if STATS["fail"] else ""))
if errors:
    uniq = list(dict.fromkeys(e[:160] for e in errors))
    raise SystemExit(f"✗ 页面报错 {len(errors)} 条（{len(uniq)} 种），前几种：\n  " + "\n  ".join(uniq[:3]) + "\n（对照 SKILL.md「踩过的坑」；-v 看完整日志）")
