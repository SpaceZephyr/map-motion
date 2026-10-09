"""太阳位置 + 地形遮挡：某地某天几点太阳在哪（方位、高度），以及考虑周围山体后「这个点几点真正见光」。
太阳位置用 NOAA 算法（误差 < 1 分钟，含大气折射）；遮挡用 dem.py 的高程沿太阳方向取地平线仰角（含地球曲率和折射）。
命令行自查：uv run --with certifi --with pillow python sun.py 98.9177 28.4114 2026-10-15   # 飞来寺
"""
import math, sys
from datetime import date, datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import dem, geo


def position(lng, lat, day, minutes, tz=8):
    """day（date）当地时 minutes（0–1440，时区 tz）→ (方位角°, 高度角°，含折射)"""
    utc = datetime(day.year, day.month, day.day) + timedelta(minutes=minutes - tz * 60)
    jd = utc.toordinal() + 1721424.5 + (utc.hour + utc.minute / 60 + utc.second / 3600) / 24
    T = (jd - 2451545) / 36525
    L0 = (280.46646 + T * (36000.76983 + 0.0003032 * T)) % 360; M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
    e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T); Mr = math.radians(M)
    C = math.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T)) + math.sin(2 * Mr) * (0.019993 - 0.000101 * T) + math.sin(3 * Mr) * 0.000289
    om = 125.04 - 1934.136 * T; lam = L0 + C - 0.00569 - 0.00478 * math.sin(math.radians(om))
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60; eps = math.radians(eps0 + 0.00256 * math.cos(math.radians(om)))
    dec = math.asin(math.sin(eps) * math.sin(math.radians(lam)))
    y = math.tan(eps / 2) ** 2; L0r = math.radians(L0)
    eqt = 4 * math.degrees(y * math.sin(2 * L0r) - 2 * e * math.sin(Mr) + 4 * e * y * math.sin(Mr) * math.cos(2 * L0r) - 0.5 * y * y * math.sin(4 * L0r) - 1.25 * e * e * math.sin(2 * Mr))
    tst = (utc.hour * 60 + utc.minute + utc.second / 60 + eqt + 4 * lng) % 1440
    ha = math.radians(tst / 4 - 180); la = math.radians(lat)
    zen = math.acos(max(-1, min(1, math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(ha))))
    az = (math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(la) - math.tan(dec) * math.cos(la))) + 180) % 360
    alt = 90 - math.degrees(zen)
    if alt > -1.5:                                                                 # 大气折射（Sæmundsson）
        alt += 1.02 / math.tan(math.radians(alt + 10.3 / (alt + 5.11))) / 60
    return az, alt


class Horizon:
    """站在 ll、眼睛海拔 h0 处，各方位地平线的仰角（°）。按需计算、0.5° 一格缓存。"""
    def __init__(self, ll, h0, reach=80):
        self.ll, self.h0, self.reach, self.cache = ll, h0, reach, {}

    def __call__(self, az):
        k = round(az * 2) / 2
        if k not in self.cache:
            best, d = -90.0, 0.25
            while d <= self.reach:
                p = geo.dest(self.ll, k, d); h = dem.at(p[0], p[1], 13 if d < 8 else 12 if d < 25 else 11)
                drop = d * d / (2 * geo.R_EARTH) * 1000 * 0.87                    # 地球曲率（扣掉约 13% 折射）
                best = max(best, math.degrees(math.atan2(h - drop - self.h0, d * 1000)))
                d += 0.1 if d < 3 else 0.3 if d < 15 else 1.0
            self.cache[k] = best
        return self.cache[k]


LIMB = 0.267                                                                       # 太阳半径：日出/见光按上沿露出算（position 已含折射，不能再用 -0.833）


def crossing(f, a, b, rising=True, step=1.0):
    """在 [a, b] 分钟里找 f(m) 第一次由负变正（rising）或由正变负的时刻（分钟，二分到 1 秒）"""
    m, prev = a, f(a)
    while m < b:
        n = min(b, m + step); cur = f(n)
        if (prev <= 0 < cur) if rising else (prev > 0 >= cur):
            lo, hi = m, n
            for _ in range(12):
                mid = (lo + hi) / 2
                if (f(mid) > 0) == rising: hi = mid
                else: lo = mid
            return hi if rising else lo
        m, prev = n, cur
    return None


def hhmm(m): m = round(m); return f"{int(m // 60) % 24:02d}:{int(m % 60):02d}"


if __name__ == "__main__":
    lng, lat = float(sys.argv[1]), float(sys.argv[2]); d = date.fromisoformat(sys.argv[3]) if len(sys.argv) > 3 else date.today()
    alt = lambda m: position(lng, lat, d, m)[1] + LIMB
    r, s = crossing(alt, 0, 720), crossing(alt, 720, 1440, rising=False)
    print(f"{d} 日出 {hhmm(r)}（方位 {position(lng, lat, d, r)[0]:.0f}°）日落 {hhmm(s)}（方位 {position(lng, lat, d, s)[0]:.0f}°）")
    hz = Horizon([lng, lat], dem.at(lng, lat) + 2)
    lit = crossing(lambda m: (lambda az, al: al + LIMB - hz(az))(*position(lng, lat, d, m)), 0, 720)
    print(f"考虑山体遮挡：{hhmm(lit) if lit else '全天不见光'} 见光")
