"""渲染进度，一行一个：python3 status.py [目录，缺省当前目录及 ~/Documents/map-motion]
读 render.py 写的 <成片>.progress；超过 2 分钟没更新的标「可能已中断」。"""
import json, sys, time
from pathlib import Path

roots = [Path(a) for a in sys.argv[1:]] or [Path.cwd(), Path.home() / "Documents/map-motion"]
found = {}
for r in roots:
    for f in r.glob("**/*.progress") if r.exists() else []:
        found[f.resolve()] = f
if not found: print("没有正在渲染的片子（完成的会删掉 .progress）"); sys.exit(0)
for f in found:
    try: d = json.loads(f.read_text())
    except Exception: continue
    stale = time.time() - d["t"] > 120
    print(f"{Path(d['out']).name}：{d['done']}/{d['total']} 帧（{d['done'] / d['total']:.0%}），已用 {d['elapsed'] // 60} 分，"
          + ("⚠ 2 分钟没更新，可能已中断" if stale else f"约剩 {max(1, round(d['eta'] / 60))} 分"))
