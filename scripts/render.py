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
    "esri": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",   # 境外卫星（WGS-84 墨卡托，全球高清）；高德卫星境外只有城市级
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
    if L.get("frames"):                                  # Live Photo 抽出的帧
        fl = []
        for fp in L["frames"]:
            f = (tl_path.parent / fp).resolve(); k = str(len(ALLOWED)); ALLOWED[k] = f; fl.append(f"/file/{k}{f.suffix}")
        L["frames"] = fl

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


def sfx_track(events, dur, path):
    """合成音效音轨：shutter＝单反快门（反光板起 + 帘幕落两下短噪声），带一点低频机身声"""
    shutter = ("(random(0)*2-1)*0.9*exp(-t*260)*lt(t,0.03)+(random(1)*2-1)*0.75*exp(-(t-0.075)*170)*between(t,0.075,0.12)"
               "+0.35*sin(2*PI*140*t)*exp(-t*60)*lt(t,0.08)")
    ins, flt = [], []
    for k, e in enumerate(events):
        if e["type"] == "clip":                          # Live Photo 原声：淡入淡出
            ins += ["-t", str(e["dur"]), "-i", e["path"]]
            flt.append(f"[{k}:a]aformat=sample_rates=44100:channel_layouts=mono,afade=t=in:d=0.25,afade=t=out:st={max(0, e['dur'] - 0.4)}:d=0.4,adelay={int(e['t'] * 1000)}:all=1[s{k}]")
            continue
        ins += ["-f", "lavfi", "-i", f"aevalsrc='{shutter}':s=44100:d=0.3"]
        flt.append(f"[{k}]highpass=f=120,adelay={int(e['t'] * 1000)}:all=1[s{k}]")
    mix = "".join(f"[s{k}]" for k in range(len(events)))
    fc = ";".join(flt) + f";{mix}amix=inputs={len(events)}:normalize=0,apad,atrim=0:{dur}[o]"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", fc, "-map", "[o]", path], check=True)


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
        if not A.audio and TL.get("sfx"):                 # 镜头里有快门等音效点且没给音乐：合成一条音效音轨
            A.audio = str(out.with_suffix(".sfx.wav")); sfx_track(TL["sfx"], TL["duration"], A.audio)
        vid = out.with_suffix(".noaudio.mp4") if A.audio else out
        ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
                               "-c:v", "libx264", "-preset", "slow", "-crf", str(A.crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(vid)], stdin=subprocess.PIPE)
        n0, n1, st = round(A.t0 * fps), round(t1 * fps), time.time()
        for i in range(n0, n1):
            ff.stdin.write(base64.b64decode(pg.evaluate(grab, i / fps)))
            if (i - n0) % (fps * 5) == 0: print(f"  {i}/{n1} 帧  {time.time() - st:.0f}s", flush=True)
        ff.stdin.close(); ff.wait()
        if A.audio:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(vid), "-ss", str(A.t0), "-i", A.audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True); vid.unlink()
        if A.audio and A.audio.endswith(".sfx.wav"): Path(A.audio).unlink(missing_ok=True)
        print("mp4 ->", out)
        if A.gif:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-vf",
                            f"fps={A.gif_fps},scale={A.gif_width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle", A.gif], check=True)
            print("gif ->", A.gif)
    b.close()
srv.shutdown()
print(f"瓦片：新取 {STATS['net']}，缓存 {STATS['cache']}，失败 {STATS['fail']}")
if errors: raise SystemExit(f"页面报错 {len(errors)} 条")
