"""公共音频件：合成音效（快门、脚步、啵、叮、嗖）和一段欢快的原创 BGM（尤克里里扫弦 + 钟琴旋律 + 贝斯 + 拍手沙锤），
按时间轴的 sfx 事件混成一条音轨。纯 Python（不用 numpy），无版权问题；BGM 的拍点和 compile 里对齐的节拍一致。

  python audio.py bgm 30 --bpm 120 --seed 3 -o bgm.wav     # 试听一段 BGM
  python audio.py sfx -o sfx.wav                            # 每种音效各来一下
render.py 用 mix(events, dur, out, music) 出音轨；music = {"bpm", "seed", "volume"} 合成，或 {"file": "xx.mp3"} 用用户的歌。
"""
import array, math, random, subprocess, sys, wave
from pathlib import Path

SR = 44100
TAU = 2 * math.pi


def _env(n, a=0.002, d=0.1):
    na = max(1, int(a * SR)); return [min(1, i / na) * math.exp(-max(0, i - na) / (d * SR)) for i in range(n)]


def _noise(n, seed):
    r = random.Random(seed); return [r.uniform(-1, 1) for _ in range(n)]


def _lp(x, k):                                                       # 一阶低通（k 越小越闷）
    y, out = 0.0, []
    for v in x: y += k * (v - y); out.append(y)
    return out


def _hp(x, k): lo = _lp(x, k); return [a - b for a, b in zip(x, lo)]


# ---------------- 音效
def shutter():
    n = int(0.3 * SR); nz = _noise(n, 1); out = [0.0] * n
    for i in range(n):
        t = i / SR
        out[i] = (nz[i] * 0.9 * math.exp(-t * 260) if t < 0.03 else 0) + (nz[i] * 0.75 * math.exp(-(t - 0.075) * 170) if 0.075 <= t < 0.12 else 0) \
            + (0.35 * math.sin(TAU * 140 * t) * math.exp(-t * 60) if t < 0.08 else 0)
    return _hp(out, 0.02)


def step(seed=0):                                                    # 软鞋底踩地：闷的噪声 + 一点低频
    n = int(0.09 * SR); nz = _lp(_noise(n, 10 + seed % 7), 0.08); f = 95 + 15 * (seed % 3)
    return [0.6 * nz[i] * math.exp(-i / (0.018 * SR)) + 0.4 * math.sin(TAU * f * i / SR) * math.exp(-i / (0.025 * SR)) for i in range(n)]


def pop():                                                           # 照片弹出「啵」：快速上滑的正弦
    n = int(0.16 * SR); ph, out = 0.0, []
    for i in range(n):
        t = i / SR; ph += TAU * (300 + 900 * (1 - math.exp(-t * 40))) / SR; out.append(0.8 * math.sin(ph) * math.exp(-t * 28) * min(1, t * 800))
    return out


def ding(hi=False):                                                  # 到站「叮」：钟琴两个泛音
    n = int(0.9 * SR); f = 1568 if hi else 1319
    return [0.5 * (math.sin(TAU * f * i / SR) + 0.35 * math.sin(TAU * f * 2.76 * i / SR) * math.exp(-i / (0.08 * SR))) * math.exp(-i / (0.32 * SR)) * min(1, i / 60) for i in range(n)]


def whoosh():                                                        # 转场「嗖」：带通噪声扫频
    n = int(0.5 * SR); nz = _noise(n, 5); out, y1, y2 = [], 0.0, 0.0
    for i in range(n):
        t = i / SR; k = 0.02 + 0.25 * math.sin(math.pi * t / 0.5) ** 2
        y1 += k * (nz[i] - y1); y2 += k * (y1 - y2); out.append((y1 - y2) * 3.2 * math.sin(math.pi * t / 0.5))
    return out


SFX = {"shutter": (shutter, 0.9), "step": (step, 0.22), "pop": (pop, 0.55), "ding": (ding, 0.45), "ding2": (lambda: ding(True), 0.45), "whoosh": (whoosh, 0.5)}


# ---------------- BGM
NOTE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
def hz(midi): return 440 * 2 ** ((midi - 69) / 12)


def pluck(f, dur, bright=0.5, seed=0):                               # Karplus-Strong：尤克里里/吉他拨弦
    n = int(dur * SR); p = max(2, int(SR / f)); r = random.Random(seed)
    buf = [r.uniform(-1, 1) for _ in range(p)]; out = [0.0] * n; k = 0.5 + 0.49 * bright
    for i in range(n):
        j = i % p; v = buf[j]; out[i] = v; buf[j] = 0.996 * (k * v + (1 - k) * buf[(j + 1) % p])
    a = int(0.003 * SR)
    for i in range(min(a, n)): out[i] *= i / a
    return out


def bell(f, dur):
    n = int(dur * SR)
    return [(math.sin(TAU * f * i / SR) + 0.25 * math.sin(TAU * f * 3.01 * i / SR) * math.exp(-i / (0.05 * SR))) * math.exp(-i / (0.35 * SR)) * min(1, i / 40) for i in range(n)]


def bassn(f, dur):
    n = int(dur * SR)
    return [(math.sin(TAU * f * i / SR) + 0.3 * math.sin(TAU * 2 * f * i / SR)) * math.exp(-i / (0.4 * SR)) * min(1, i / 100) * min(1, (n - i) / 300) for i in range(n)]


def kick():
    n = int(0.25 * SR); ph, out = 0.0, []
    for i in range(n):
        t = i / SR; ph += TAU * (50 + 110 * math.exp(-t * 30)) / SR; out.append(math.sin(ph) * math.exp(-t * 14))
    return out


def clap():
    n = int(0.2 * SR); nz = _hp(_noise(n, 77), 0.2); out = []
    for i in range(n):
        t = i / SR; e = sum(math.exp(-(t - o) * 90) for o in (0, 0.011, 0.022) if t >= o) / 3 + 0.5 * math.exp(-t * 18)
        out.append(nz[i] * e)
    return out


def shaker(seed):
    n = int(0.06 * SR); nz = _hp(_noise(n, seed), 0.6)
    return [nz[i] * math.exp(-i / (0.012 * SR)) * min(1, i / 200) for i in range(n)]


def bgm(dur, bpm=120, seed=1, key="C"):
    """dur 秒的欢快 BGM（I–V–vi–IV）。第一小节只有扫弦，最后一小节停在主和弦上收尾"""
    rnd = random.Random(seed); b = 60 / bpm; bar = 4 * b; n = int((dur + 1.2) * SR); mix = [0.0] * n
    root = 60 + NOTE.get(key[0], 0)
    prog = [[0, 4, 7], [7, 11, 14], [9, 12, 16], [5, 9, 12]]           # I V vi IV（相对主音的半音）
    if seed % 2: prog = [[0, 4, 7], [9, 12, 16], [5, 9, 12], [7, 11, 14]]   # I vi IV V
    cache = {}

    def put(sig, t, g):
        s = int(t * SR)
        for i, v in enumerate(sig):
            if s + i >= n: break
            mix[s + i] += v * g

    def cached(k, fn):
        if k not in cache: cache[k] = fn()
        return cache[k]
    nbars = max(2, int(math.ceil(dur / bar)))
    scale = [0, 2, 4, 7, 9, 12, 14, 16]                                  # 大调五声 + 八度
    motif = [rnd.choice([None, 0, 2, 4, 4, 5, 7]) for _ in range(8)]     # 一小节 8 个八分音符的动机，每两小节变一点
    strum = [(0, 1, 1.0), (1, 1, 0.75), (1.5, -1, 0.6), (2.5, -1, 0.6), (3, 1, 0.8), (3.5, -1, 0.6)]   # (拍, 方向, 力度) 下 下上 上下上
    for bi in range(nbars):
        t0 = bi * bar; ch = prog[bi % 4]; last = bi == nbars - 1
        chord = [root + ch[0] - 12 + 7, root + ch[0], root + ch[1], root + ch[2]]     # 四根弦（G C E A 的感觉）
        for (bt, dirn, vel) in (strum if not last else [(0, 1, 1.0)]):
            order = chord if dirn > 0 else chord[::-1]
            for k, m in enumerate(order):
                put(cached(("u", m), lambda m=m: pluck(hz(m), 1.4 if last else 0.7, 0.55, m)), t0 + bt * b + k * 0.012 + rnd.uniform(0, 0.004), 0.16 * vel)
        if bi == 0 and nbars > 3: continue                               # 前奏只有尤克里里
        for bt in ((0, 2) if not last else (0,)):
            put(cached(("b", ch[0]), lambda: bassn(hz(root + ch[0] - 24), b * 1.8)), t0 + bt * b, 0.32)
        if not last:
            for bt in (0, 2): put(cached("k", kick), t0 + bt * b, 0.45)
            for bt in (1, 3): put(cached("c", clap), t0 + bt * b, 0.28)
            for e in range(8): put(cached(("s", e % 2), lambda e=e: shaker(e)), t0 + e * b / 2 + 0.01, 0.08 if e % 2 else 0.05)
            if bi % 2 == 0 and bi > 0: motif = [m if rnd.random() < 0.7 else rnd.choice([None, 0, 2, 4, 5, 7]) for m in motif]
            if bi >= 2:                                                   # 钟琴旋律从第三小节进
                for e, m in enumerate(motif):
                    if m is None: continue
                    deg = scale[min(len(scale) - 1, m + (ch[0] in (7, 9) and m < 5))]
                    put(cached(("m", deg), lambda d=deg: bell(hz(root + 12 + d), 0.6)), t0 + e * b / 2, 0.13)
        else:
            put(cached(("m", 12), lambda: bell(hz(root + 24), 1.5)), t0, 0.16)
    fo = int(1.2 * SR); end = int(dur * SR)                              # 结尾 1.2 秒淡出，裁到 dur
    for i in range(max(0, end - fo), min(n, end)): mix[i] *= (end - i) / fo
    return mix[:end]


# ---------------- 混音
def _write(path, x):
    pk = max(1e-6, max(abs(v) for v in x)); g = min(1.0, 0.89 / pk)
    a = array.array("h", (int(max(-1, min(1, v * g)) * 32767) for v in x))
    with wave.open(str(path), "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(a.tobytes())


def mix(events, dur, out, music=None):
    """events: [{"t", "type", ...}]；clip 类（Live Photo 原声）交给 ffmpeg 混；music 见模块说明"""
    n = int(dur * SR); x = [0.0] * n; cache = {}
    for e in events:
        if e["type"] not in SFX: continue
        fn, g = SFX[e["type"]]; key = (e["type"], e.get("v", 0) % 3 if e["type"] == "step" else 0)
        if key not in cache: cache[key] = fn(e.get("v", 0)) if e["type"] == "step" else fn()
        s = int(e["t"] * SR); g *= e.get("gain", 1)
        for i, v in enumerate(cache[key]):
            if 0 <= s + i < n: x[s + i] += v * g
    if music and not music.get("file"):
        m = bgm(dur, music.get("bpm", 120), music.get("seed", 1), music.get("key", "C")); vol = music.get("volume", 0.55)
        for i in range(min(n, len(m))): x[i] += m[i] * vol
    out = Path(out); _write(out, x)
    clips = [e for e in events if e["type"] == "clip"]
    if (music and music.get("file")) or clips:                         # 用户的歌 / Live 原声：ffmpeg 叠上去
        ins, flt, k = ["-i", str(out)], ["[0:a]anull[s0]"], 1
        if music and music.get("file"):
            ins += ["-stream_loop", "-1", "-i", music["file"]]
            flt.append(f"[{k}:a]aformat=sample_rates={SR}:channel_layouts=mono,atrim=0:{dur},afade=t=out:st={max(0, dur - 1.5)}:d=1.5,volume={music.get('volume', 0.7)}[s{k}]"); k += 1
        for e in clips:
            ins += ["-t", str(e["dur"]), "-i", e["path"]]
            flt.append(f"[{k}:a]aformat=sample_rates={SR}:channel_layouts=mono,afade=t=in:d=0.25,afade=t=out:st={max(0, e['dur'] - 0.4)}:d=0.4,adelay={int(e['t'] * 1000)}:all=1[s{k}]"); k += 1
        tmp = out.with_suffix(".mix.wav")
        fc = ";".join(flt) + ";" + "".join(f"[s{i}]" for i in range(k)) + f"amix=inputs={k}:normalize=0,apad,atrim=0:{dur},alimiter=limit=0.95[o]"
        subprocess.run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", fc, "-map", "[o]", str(tmp)], check=True); tmp.replace(out)
    tmp = out.with_suffix(".ln.wav")                                    # 响度归一到 -16 LUFS（短视频平台常用），峰值留 1.5 dB
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), str(tmp)], check=True); tmp.replace(out)
    return str(out)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("what", choices=["bgm", "sfx"]); ap.add_argument("dur", nargs="?", type=float, default=20)
    ap.add_argument("--bpm", type=int, default=120); ap.add_argument("--seed", type=int, default=1); ap.add_argument("-o", default="out.wav"); a = ap.parse_args()
    if a.what == "bgm": _write(a.o, bgm(a.dur, a.bpm, a.seed))
    else: mix([{"t": 0.3 + 0.8 * i, "type": k} for i, k in enumerate(SFX)], 0.8 * len(SFX) + 1, a.o)
    print(a.o)
