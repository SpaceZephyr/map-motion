#!/bin/zsh
# 一键：镜头表 → 时间轴 → 成片。用法：make.sh spec.json 成片.mp4 [render.py 的其它参数，如 --gif x.gif / --stills 0,3 / --audio a.wav]
set -e
D="${0:A:h}"; SPEC="${1:A}"; OUT="$2"; shift 2
TL="${SPEC:r}.timeline.json"
uv run --with certifi python "$D/compile.py" "$SPEC" --out "$TL"
uv run --with playwright --with certifi python "$D/render.py" "$TL" --out "$OUT" "$@"
