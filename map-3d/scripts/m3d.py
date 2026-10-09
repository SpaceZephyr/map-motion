"""3D 地形片的辅助命令（编译和渲染交给 map-motion 引擎：scripts/compile.py、render.py）。

  check spec.json [-o 拼图.png]   编译 → 在每个关键时刻前渲 0.6 秒连续小段 → 取末帧拼成一张图（单帧 --stills 抓不到连续出帧才有的黑块/断边）
  make  spec.json 成片.mp4        编译 + 整片渲染 + 270px 预览 GIF（约 1 秒一帧，放后台跑）
  gif   成片.mp4 [-o x.gif]       只做预览 GIF
"""
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENG = HERE.parents[1] / "scripts"                                   # 同一仓库里的引擎
if not (ENG / "terrain3d.py").exists(): ENG = Path.home() / ".claude/skills/map-motion/scripts"
UV = ["uv", "run", "-q", "--with", "certifi", "--with", "pillow", "--with", "playwright", "python"]


def compile_(spec):
    tl = spec.with_name(spec.stem + ".timeline.json")
    subprocess.run(UV + [str(ENG / "compile.py"), str(spec), "--out", str(tl)], check=True); return tl


def render(tl, *args):
    r = subprocess.run(UV + [str(ENG / "render.py"), str(tl), *args], capture_output=True, text=True)
    keep = [l for l in (r.stdout + r.stderr).splitlines() if not any(k in l for k in ("GL Driver", "performance warning"))]
    if r.returncode: print("\n".join(keep[-15:])); raise SystemExit("渲染失败")
    return keep


def gif(video, out=None):
    out = out or str(Path(video).with_suffix(".gif"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                    "fps=10,scale=270:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4", out], check=True)
    print("gif ->", out)


def cmd_check(a):
    spec = Path(a.spec).resolve(); tl = compile_(spec); T = json.loads(tl.read_text()); P = T["phase"]
    if T.get("place"): ts = [P["dive"] * 0.5, P["dive"] - 0.2, P["dive"] + 2, (P["dive"] + T["duration"]) / 2, T["duration"] - 0.1]
    else: ts = [P["dive"] - 0.2, P["ov"] - 0.2, P["f0"] + 1.5, (P["f0"] + P["f1"]) / 2, P["f1"] + 0.3, T["duration"] - 0.1]
    d = spec.parent / (spec.stem + "-check"); d.mkdir(exist_ok=True); shots = []
    for t in ts:
        seg = d / f"seg_{t:05.1f}.mp4"; render(tl, "--from", f"{max(0, t - 0.6):.2f}", "--to", f"{t:.2f}", "--out", str(seg))
        png = d / f"t{t:05.1f}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.05", "-i", str(seg), "-frames:v", "1", "-vf", "scale=360:-2", str(png)], check=True)
        seg.unlink(); shots.append(png); print(f"  {t:5.1f}s ok")
    out = a.o or str(spec.with_name(spec.stem + "-check.png"))
    ins = sum((["-i", str(s)] for s in shots), [])
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", "".join(f"[{i}]" for i in range(len(shots))) + f"hstack={len(shots)}", out], check=True)
    print("拼图 ->", out, "（时刻：" + "、".join(f"{t:.1f}s" for t in ts) + "）")


def cmd_make(a):
    spec = Path(a.spec).resolve(); tl = compile_(spec); out = Path(a.out).resolve()
    for l in render(tl, "--out", str(out)):
        if "->" in l or "瓦片" in l or "报错" in l: print(l)
    gif(out)


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sp = ap.add_subparsers(dest="cmd", required=True)
p = sp.add_parser("check"); p.add_argument("spec"); p.add_argument("-o"); p.set_defaults(fn=cmd_check)
p = sp.add_parser("make"); p.add_argument("spec"); p.add_argument("out"); p.set_defaults(fn=cmd_make)
p = sp.add_parser("gif"); p.add_argument("video"); p.add_argument("-o"); p.set_defaults(fn=lambda a: gif(a.video, a.o))
a = ap.parse_args(); a.fn(a)
