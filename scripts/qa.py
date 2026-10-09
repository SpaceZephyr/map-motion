"""渲染时的自动质检：把页面（runtime/qa.js）交回的每帧文字框、照片框、黑块比例，判成几行文字结论。
规则：
  出画  文字或照片有一部分伸出画面（整段都在画外的不算——那是镜头外的地名，观众看不到）
  重叠  两段不同的文字互相压住（交叠面积 > 较小者的 25%）；文字压住照片（> 文字面积的 30%）
  黑块  纯黑像素（RGB 都 < 3）> 3%（3D 片远处瓦片漏画、天空没出来；太空阶段运行时自己跳过）
同一问题在相邻抽样时刻反复出现时合并成一个时间段，按持续时间排序；整片模式下持续不到 1 秒的出画/重叠不报（镜头运动时地名滑过边缘是正常的），静帧模式全报。
"""
import json, re

BLACK = 0.03


def _inter(a, b):
    w = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]); h = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
    return max(0, w) * max(0, h)


def _area(a): return max(1, (a["x1"] - a["x0"]) * (a["y1"] - a["y0"]))


def frame_issues(q, W, H):
    seen, boxes = set(), []
    for b in q.get("boxes", []):                                   # 描边 + 填充、阴影两遍画的同一段字只算一次
        k = (b["k"], b["s"], round(b["x0"] / 6), round(b["y0"] / 6))
        if k not in seen: seen.add(k); boxes.append(b)
    out = []
    for b in boxes:
        if b["x1"] < 0 or b["x0"] > W or b["y1"] < 0 or b["y0"] > H: continue
        over = max(-b["x0"], b["x1"] - W, -b["y0"], b["y1"] - H)
        if over > 6:
            side = "左" if b["x0"] < 0 else "右" if b["x1"] > W else "上" if b["y0"] < 0 else "下"
            out.append(("出画", f"{'照片' if b['k'] == 'image' else '「' + b['s'][:14] + '」'} 从{side}边出画 {over:.0f}px"))
    texts = [b for b in boxes if b["k"] == "text" and 0 <= (b["x0"] + b["x1"]) / 2 <= W and 0 <= (b["y0"] + b["y1"]) / 2 <= H]
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if a["s"] == b["s"] or a["s"] in b["s"] or b["s"] in a["s"]: continue
            if _inter(a, b) > 0.25 * min(_area(a), _area(b)):
                p = sorted([a["s"][:12], b["s"][:12]]); out.append(("重叠", f"「{p[0]}」压「{p[1]}」"))
        for im in (x for x in boxes if x["k"] == "image"):
            if _inter(a, im) > 0.3 * _area(a) and not (im["x0"] <= a["x0"] and a["x1"] <= im["x1"] and im["y0"] <= a["y0"] and a["y1"] <= im["y1"]):
                out.append(("重叠", f"「{a['s'][:12]}」压住照片"))
    if q.get("black") is not None and q["black"] > BLACK: out.append(("黑块", f"黑块 {q['black'] * 100:.0f}%"))
    return out


def summarize(samples, W, H, step, min_dur=1.0):
    """samples: [(t, qa)] → (问题行列表, 原始明细)"""
    hits = {}
    for t, q in samples:
        for kind, msg in set(frame_issues(q, W, H)):
            key = (kind, re.sub(r"\s*\d+(px|%)$", "", msg))                  # 同一标签不同像素数算一件事
            hits.setdefault(key, []).append((t, msg))
    lines = []
    for (kind, key), ts in hits.items():
        spans, cur = [], [ts[0][0], ts[0][0]]
        for t, _ in ts[1:]:
            if t - cur[1] <= step * 1.6: cur[1] = t
            else: spans.append(cur); cur = [t, t]
        spans.append(cur)
        if kind != "黑块": spans = [sp for sp in spans if sp[1] - sp[0] + step >= min_dur]   # 镜头运动时地名滑过边缘、照片飞入飞出：每一段都一闪而过的不报
        if not spans: continue
        dur = sum(b - a + step for a, b in spans)
        where = "、".join(f"{a:.1f}s" if b - a < step / 2 else f"{a:.1f}–{b:.1f}s" for a, b in spans[:4]) + ("…" if len(spans) > 4 else "")
        worst = max(int(re.search(r"(\d+)(px|%)$", m).group(1)) if re.search(r"(\d+)(px|%)$", m) else 0 for _, m in ts)
        msg = key + (f" 最多 {worst}{'%' if kind == '黑块' else 'px'}" if worst else "")
        lines.append((dur, f"{kind}  {msg}  @ {where}"))
    lines.sort(key=lambda x: -x[0])
    return [l for _, l in lines], {f"{t:.2f}": frame_issues(q, W, H) for t, q in samples}


def report(samples, W, H, step, path=None, limit=8):
    lines, detail = summarize(samples, W, H, step, 1.0 if step < 10 else 0)
    if path: path.write_text(json.dumps({"issues": lines, "frames": detail}, ensure_ascii=False, indent=1))
    if not lines: return f"质检：通过（抽查 {len(samples)} 帧：无出画、无重叠、无黑块）"
    more = f"\n  …另有 {len(lines) - limit} 项，见 {path.name}" if path and len(lines) > limit else ""
    return f"质检：{len(lines)} 项问题（抽查 {len(samples)} 帧）\n" + "\n".join("  ✗ " + l for l in lines[:limit]) + more
