"""timeline.json → MP4 / GIF / 静帧。起本地服务（运行时 + 内置底图 + 高德瓦片代理与缓存）→ 无头 Chromium 逐帧画 → ffmpeg。

uv run --with playwright --with certifi python render.py timeline.json --out 成片.mp4 [--gif 动图.gif] [--audio 配乐.wav]
uv run --with playwright --with certifi python render.py timeline.json --stills 0,2.5,6 --out 静帧目录/
首次用：uv run --with playwright playwright install chromium

瓦片缓存在 ~/.cache/map-motion/tiles/（同一片子重渲不再请求）。页面报错 → 非零退出。
"""
import argparse, base64, functools, http.server, json, socketserver, ssl, subprocess, threading, time, urllib.parse, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
ASSETS = HERE.parent / "assets"
TCACHE = Path.home() / ".cache/map-motion/tiles"
SRC = {   # 高德瓦片（GCJ-02 墨卡托）：amap＝标准路网 512px，sat＝卫星 256px，lbl＝卫星上的路名地名叠加 512px
    "amap": "https://wprd0{s}.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=2&style=7",
    "sat": "https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}",
    "lbl": "https://wprd0{s}.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=2&style=8&ltype=4",
}

ap = argparse.ArgumentParser()
ap.add_argument("timeline"); ap.add_argument("--out", required=True)
ap.add_argument("--stills"); ap.add_argument("--gif"); ap.add_argument("--audio")
ap.add_argument("--gif-width", type=int, default=480); ap.add_argument("--gif-fps", type=int, default=12)
ap.add_argument("--crf", type=int, default=20); ap.add_argument("--from", dest="t0", type=float, default=0); ap.add_argument("--to", dest="t1", type=float)
A = ap.parse_args()

tl_path = Path(A.timeline).resolve(); TL = json.loads(tl_path.read_text())
ALLOWED = {}
for L in TL["layers"]:                                   # 本地图片（照片）→ /file/<序号>，只服务点名的文件
    if L.get("image") and not L["image"].startswith(("http:", "https:", "data:")):
        f = (tl_path.parent / L["image"]).resolve()
        if not f.exists(): raise SystemExit(f"图片不存在：{L['image']}")
        k = str(len(ALLOWED)); ALLOWED[k] = f; L["image"] = f"/file/{k}{f.suffix}"

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
            return self._send(d, "image/jpeg" if src == "sat" else "image/png") if d else self.send_error(404)
        if p.startswith("/asset/"):
            f = (ASSETS / p[len("/asset/"):]).resolve()
            if ASSETS in f.parents and f.exists(): return self._send(f.read_bytes(), "font/woff" if f.suffix == ".woff" else "application/json")
            return self.send_error(404)
        if p.startswith("/file/"):
            f = ALLOWED.get(Path(p).stem)
            return self._send(f.read_bytes(), "image/jpeg" if f.suffix.lower() in (".jpg", ".jpeg") else "image/png") if f else self.send_error(404)
        return super().do_GET()


class TS(socketserver.ThreadingMixIn, socketserver.TCPServer): daemon_threads = True
srv = TS(("127.0.0.1", 0), functools.partial(Q, directory=str(HERE / "runtime")))
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]

errors = []
with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--disable-web-security"])
    pg = b.new_page(viewport={"width": TL["width"], "height": TL["height"]}, device_scale_factor=1)
    pg.on("console", lambda m: (print("[page]", m.text), errors.append(m.text)) if m.type == "error" else None)
    pg.on("pageerror", lambda e: (print("[pageerror]", e), errors.append(str(e))))
    pg.add_init_script("window.MM_TIMELINE = " + json.dumps(TL, ensure_ascii=False) + ";")
    pg.goto(f"http://127.0.0.1:{port}/index.html")
    pg.wait_for_function("window.__ready === true || !!window.__bootFailed", timeout=120000)
    if pg.evaluate("window.__bootFailed || null"): raise SystemExit("运行时启动失败：\n" + pg.evaluate("window.__bootFailed"))
    grab = "async (t) => { await window.prepare(t); window.renderFrame(t); return window.__canvas.toDataURL('image/png').split(',')[1]; }"
    fps, t1 = TL["fps"], A.t1 if A.t1 is not None else TL["duration"]
    if A.stills:
        out = Path(A.out); out.mkdir(parents=True, exist_ok=True)
        for s in A.stills.split(","):
            (out / f"t{float(s):06.2f}.png").write_bytes(base64.b64decode(pg.evaluate(grab, float(s))))
        print("stills ->", out)
    else:
        out = Path(A.out); out.parent.mkdir(parents=True, exist_ok=True)
        vid = out.with_suffix(".noaudio.mp4") if A.audio else out
        ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
                               "-c:v", "libx264", "-preset", "slow", "-crf", str(A.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(vid)], stdin=subprocess.PIPE)
        n0, n1, st = round(A.t0 * fps), round(t1 * fps), time.time()
        for i in range(n0, n1):
            ff.stdin.write(base64.b64decode(pg.evaluate(grab, i / fps)))
            if (i - n0) % (fps * 5) == 0: print(f"  {i}/{n1} 帧  {time.time() - st:.0f}s", flush=True)
        ff.stdin.close(); ff.wait()
        if A.audio:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-i", A.audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True); vid.unlink()
        print("mp4 ->", out)
        if A.gif:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-vf",
                            f"fps={A.gif_fps},scale={A.gif_width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", A.gif], check=True)
            print("gif ->", A.gif)
    b.close()
srv.shutdown()
print(f"瓦片：新取 {STATS['net']}，缓存 {STATS['cache']}，失败 {STATS['fail']}")
if errors: raise SystemExit(f"页面报错 {len(errors)} 条")
