// map-motion 3D 地形运行时：MapLibre GL（地球投影 + raster-dem 地形 + Esri 卫星）画地图和轨迹线，2D 画布叠 HUD。
// 坐标 WGS-84。逐帧相机由 terrain3d.py 算好（TL.frames[i] = [lng, lat, zoom, pitch, bearing, 已走 km]）。
// 对外接口和 mm.js 一样：window.prepare(t)（异步，等瓦片）→ window.renderFrame(t) → window.__canvas。
(() => {
'use strict';
const TL = window.MM_TIMELINE, W = TL.width, H = TL.height, U = Math.min(W, H) / 1080, PH = TL.phase;
const cv = document.getElementById('c'), c = cv.getContext('2d'); cv.width = W; cv.height = H; window.__canvas = cv;
const md = document.getElementById('m'); md.style.width = W + 'px'; md.style.height = H + 'px';
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), lerp = (a, b, e) => a + (b - a) * e;
const E = {
  smooth: p => { p = clamp(p); return p * p * p * (p * (6 * p - 15) + 10); },
  out: p => 1 - Math.pow(1 - clamp(p), 3),
  back: p => { p = clamp(p); const s = 1.7, q = p - 1; return 1 + (s + 1) * q * q * q + s * q * q; },
};
const fade = (t, a, b, fi = 0.5, fo = 0.5) => clamp((t - a) / fi) * (b == null ? 1 : clamp((b - t) / fo));
const Y = TL.color, TR = TL.track, ST = TL.stats, STEP = TR[1][3] - TR[0][3];
const FONT = (f, s) => `${s * U}px "${f}", "PingFang SC", sans-serif`;

// 轨迹上第 d km 的点：[lng, lat, 海拔, km, 累计爬升]
function at(d) {
  const x = clamp(d / STEP, 0, TR.length - 1), i = Math.min(TR.length - 2, Math.floor(x)), f = x - i, a = TR[i], b = TR[i + 1];
  return a.map((v, k) => lerp(v, b[k], f));
}
const lineTo = d => { const i = Math.min(TR.length - 1, Math.floor(d / STEP)); const pts = TR.slice(0, i + 1).map(p => [p[0], p[1]]); const e = at(d); pts.push([e[0], e[1]]); return pts; };
const gj = coords => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords.length > 1 ? coords : [coords[0], coords[0]] } });

let map; const IMG = {};
async function boot() {
  for (const [fam, f] of [['MM-Bold', 'NotoSansSC-700'], ['MM-Black', 'NotoSansSC-900'], ['MM-Hand', 'LXGWWenKai-500'], ['MM-Num', 'Anton-400']]) {
    const ff = new FontFace(fam, `url(/asset/fonts/${f}.woff)`); await ff.load(); document.fonts.add(ff);
  }
  await Promise.all(TL.layers.map(L => new Promise((res, rej) => { const im = new Image(); im.onload = () => { IMG[L.image] = im; res(); }; im.onerror = () => rej(new Error('图片加载失败 ' + L.image)); im.src = L.image; })));
  const f0 = TL.frames[0];
  map = new maplibregl.Map({
    container: 'm', interactive: false, attributionControl: false, pixelRatio: 1, fadeDuration: 0, maxPitch: 85,
    canvasContextAttributes: { preserveDrawingBuffer: true, antialias: true },
    center: [f0[0], f0[1]], zoom: f0[2], pitch: f0[3], bearing: f0[4],
    style: {
      version: 8, projection: { type: 'globe' },
      sky: { 'sky-color': '#5b8fd0', 'horizon-color': '#d6e4f2', 'fog-color': '#c9d8e8', 'sky-horizon-blend': 0.55, 'horizon-fog-blend': 0.7, 'fog-ground-blend': 0.85,
             'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 1, 5, 1, 8, 0] },
      sources: {
        sat: { type: 'raster', tiles: ['/tile/esri/{z}/{x}/{y}'], tileSize: 256, maxzoom: 18 },
        dem: { type: 'raster-dem', tiles: ['/tile/dem/{z}/{x}/{y}'], encoding: 'terrarium', tileSize: 256, maxzoom: 14 },
        full: { type: 'geojson', data: gj([[TR[0][0], TR[0][1]]]) },
        done: { type: 'geojson', data: gj([[TR[0][0], TR[0][1]]]) },
      },
      layers: [
        { id: 'sat', type: 'raster', source: 'sat', paint: { 'raster-fade-duration': 0, 'raster-saturation': 0.05, 'raster-contrast': 0.08 } },
        { id: 'full-case', type: 'line', source: 'full', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#000', 'line-opacity': 0.35, 'line-width': 7 * U, 'line-blur': 3 * U } },
        { id: 'full', type: 'line', source: 'full', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#fff', 'line-opacity': 0.92, 'line-width': 4 * U } },
        { id: 'done-glow', type: 'line', source: 'done', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': Y, 'line-opacity': 0.45, 'line-width': 22 * U, 'line-blur': 12 * U } },
        { id: 'done', type: 'line', source: 'done', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': Y, 'line-width': 7 * U } },
      ],
      terrain: { source: 'dem', exaggeration: TL.exaggeration },
    },
  });
  map.on('error', e => console.warn('[maplibre]', e.error && e.error.message));
  await new Promise(r => map.once('load', r));
}

let lastFull = -1, lastDone = -1;
function settle() {
  return new Promise(res => {
    let ok = false; const fin = () => { if (!ok) { ok = true; res(); } };
    map.once('idle', fin); map.triggerRepaint();
    setTimeout(() => { if (!ok) { console.warn('等瓦片超时，照常出帧'); fin(); } }, 45000);
  });
}
function setData(id, data) {                                             // setData 在 worker 里异步处理，idle 可能先到：等这条源真正换上新数据
  return new Promise(res => {
    const h = e => { if (e.sourceId === id && e.isSourceLoaded) { map.off('sourcedata', h); res(); } };
    map.on('sourcedata', h); map.getSource(id).setData(data); setTimeout(() => { map.off('sourcedata', h); res(); }, 10000);
  });
}
let F, curProj = 'globe';
window.prepare = async t => {
  const i = clamp(Math.round(t * TL.fps), 0, TL.frames.length - 1); F = TL.frames[i];
  const pj = F[2] > 12.2 ? 'mercator' : 'globe';                           // 推近后换平面投影：地球投影下雾和天空不生效，远处地形会露出生硬的断边
  if (pj !== curProj) { map.setProjection({ type: pj }); curProj = pj; }
  map.jumpTo({ center: [F[0], F[1]], zoom: F[2], pitch: F[3], bearing: F[4] });
  const rv = E.smooth((t - PH.dive + 0.8) / 1.8);                           // 俯冲收尾时白线从起点画到终点
  const fk = Math.round(rv * 1000);
  const pend = [];
  if (fk !== lastFull && !TL.place) { pend.push(setData('full', gj(lineTo(rv * ST.km)))); lastFull = fk; }
  const dk = Math.round(F[5] * 2000);
  if (dk !== lastDone) { pend.push(setData('done', gj(F[5] > 0 ? lineTo(F[5]) : [[TR[0][0], TR[0][1]]]))); lastDone = dk; }
  map.setPaintProperty('done', 'line-opacity', F[5] > 0.001 ? 1 : 0); map.setPaintProperty('done-glow', 'line-opacity', F[5] > 0.001 ? 0.45 : 0);
  await Promise.all(pend); await settle();
  for (let k = 0; k < 6 && !map.areTilesLoaded(); k++) await settle();   // 连续出帧时远处地形瓦片会漏：没齐就再等
};

// ================= HUD
const proj = (ll, ele) => { const p = map.project(ll); return [p.x, p.y]; };
const onScreen = p => p[0] > -50 && p[0] < W + 50 && p[1] > -50 && p[1] < H + 50;
function shadowText(txt, x, y, font, color = '#fff', align = 'left', blur = 14) {
  c.save(); c.font = font; c.textAlign = align; c.textBaseline = 'alphabetic'; c.shadowColor = 'rgba(0,0,0,.75)'; c.shadowBlur = blur * U; c.shadowOffsetY = 2 * U;
  c.fillStyle = color; c.fillText(txt, x, y); c.shadowBlur = 0; c.shadowOffsetY = 0; c.fillText(txt, x, y); c.restore();
}
function numText(txt, x, y, size, color = Y, align = 'left') {           // Anton 加斜切，接近参考图的斜体数字
  c.save(); c.translate(x, y); c.transform(1, 0, -0.16, 1, 0, 0); shadowText(txt, 0, 0, `${size * U}px "MM-Num"`, color, align, 16); c.restore();
}
const fmt = v => Math.round(v).toLocaleString('en-US');

function drawMarks(t, a) {
  if (a <= 0) return;
  for (const m of TL.marks) {
    const p = proj(m.at); if (!onScreen(p)) continue;
    c.save(); c.globalAlpha = a * clamp((p[1] - 290 * U) / (60 * U));        // 别压住顶部的标题和里程
    c.fillStyle = '#fff'; c.beginPath(); c.arc(p[0], p[1], 6 * U, 0, 7); c.fill(); c.lineWidth = 2 * U; c.strokeStyle = 'rgba(0,0,0,.6)'; c.stroke();
    const lab = m.ele ? `${m.name} ${fmt(m.ele)}m` : m.name;
    c.font = FONT('MM-Bold', 30); c.lineJoin = 'round'; c.strokeStyle = 'rgba(0,0,0,.72)'; c.lineWidth = 7 * U; c.textBaseline = 'middle';
    c.strokeText(lab, p[0] + 14 * U, p[1]); c.fillStyle = '#fff'; c.fillText(lab, p[0] + 14 * U, p[1]); c.restore();
  }
}

function drawHiker(t, d, a) {
  if (a <= 0) return; const e = at(d), p = proj([e[0], e[1]]);
  c.save(); c.globalAlpha = a;
  const pulse = (t * 1.2) % 1; c.strokeStyle = Y; c.lineWidth = 4 * U * (1 - pulse); c.globalAlpha = a * (1 - pulse);
  c.beginPath(); c.arc(p[0], p[1], (16 + 40 * pulse) * U, 0, 7); c.stroke(); c.globalAlpha = a;
  const g = c.createRadialGradient(p[0], p[1], 0, p[0], p[1], 34 * U); g.addColorStop(0, 'rgba(255,250,170,.9)'); g.addColorStop(1, 'rgba(255,240,60,0)');
  c.fillStyle = g; c.beginPath(); c.arc(p[0], p[1], 34 * U, 0, 7); c.fill();
  c.fillStyle = '#fff'; c.beginPath(); c.arc(p[0], p[1], 13 * U, 0, 7); c.fill(); c.fillStyle = Y; c.beginPath(); c.arc(p[0], p[1], 9 * U, 0, 7); c.fill();
  c.restore();
}

function card(im, x, y, size, a, label) {                                // 白边照片牌 + 下方尖角，尖角对准地面那一点
  const r = im.width / im.height, w = r >= 1 ? size : size * r, h = r >= 1 ? size / r : size, b = 6 * U * size / 160, stem = 26 * U * size / 160;
  const bx = x - w / 2, by = y - stem - h - b * 2;
  c.save(); c.globalAlpha = a; c.shadowColor = 'rgba(0,0,0,.5)'; c.shadowBlur = 18 * U; c.shadowOffsetY = 6 * U;
  c.fillStyle = '#fff'; c.beginPath(); c.roundRect(bx - b, by, w + 2 * b, h + 2 * b, 8 * U);
  c.moveTo(x - stem * 0.55, by + h + 2 * b - 1); c.lineTo(x, y); c.lineTo(x + stem * 0.55, by + h + 2 * b - 1); c.fill();
  c.shadowBlur = 0; c.shadowOffsetY = 0; c.save(); c.beginPath(); c.roundRect(bx, by + b, w, h, 4 * U); c.clip(); c.drawImage(im, bx, by + b, w, h); c.restore();
  if (label) { c.font = FONT('MM-Bold', Math.max(24, size / 8.5) / 1); c.textAlign = 'center'; c.lineJoin = 'round'; c.lineWidth = 7 * U; c.strokeStyle = 'rgba(0,0,0,.7)';
    c.strokeText(label, x, by - 14 * U); c.fillStyle = '#fff'; c.fillText(label, x, by - 14 * U); }
  c.restore();
}

function drawPhotos(t) {
  for (const L of TL.layers) {
    const th = L.t_hit; if (t < th - 0.15) continue;
    const pop = E.back((t - th + 0.15) / 0.55), big = fade(t, th, th + 2.0, 0.3, 0.6), fin = E.smooth((t - PH.f1 - 1.2) / 1.2);
    const size = (lerp(150, 330, big) + 40 * fin) * U * pop;
    const p = proj(L.at); if (!onScreen(p)) continue;
    card(IMG[L.image], p[0], p[1], size, clamp(pop * 2), big > 0.5 || fin > 0.5 ? L.label : '');
  }
}

// 小地图（北朝上）
const MM = (() => {
  const ms = TR.map(p => { const s = Math.sin(p[1] * Math.PI / 180); return [(p[0] + 180) / 360, 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)]; });
  const xs = ms.map(m => m[0]), ys = ms.map(m => m[1]), x0 = Math.min(...xs), y0 = Math.min(...ys), sw = Math.max(...xs) - x0, sh = Math.max(...ys) - y0;
  const box = 190 * U, s = box / Math.max(sw, sh);
  return { pts: ms.map(m => [(m[0] - x0) * s + (box - sw * s) / 2, (m[1] - y0) * s + (box - sh * s) / 2]), box };
})();
function drawMinimap(d, a, x, y) {
  if (a <= 0) return; const n = Math.min(MM.pts.length - 1, Math.floor(d / STEP));
  c.save(); c.globalAlpha = a; c.translate(x, y); c.lineJoin = c.lineCap = 'round';
  const path = (k0, k1) => { c.beginPath(); for (let k = k0; k <= k1; k++) k === k0 ? c.moveTo(...MM.pts[k]) : c.lineTo(...MM.pts[k]); };
  c.shadowColor = 'rgba(0,0,0,.7)'; c.shadowBlur = 8 * U; c.strokeStyle = 'rgba(255,255,255,.85)'; c.lineWidth = 5 * U; path(0, MM.pts.length - 1); c.stroke();
  c.shadowBlur = 0; if (n > 0) { c.strokeStyle = Y; c.lineWidth = 6 * U; path(0, n); c.stroke(); }
  const q = MM.pts[n]; c.fillStyle = 'rgba(255,255,255,.35)'; c.beginPath(); c.arc(q[0], q[1], 16 * U, 0, 7); c.fill(); c.fillStyle = Y; c.beginPath(); c.arc(q[0], q[1], 9 * U, 0, 7); c.fill();
  c.restore();
}

function drawProfile(d, a) {
  if (a <= 0) return;
  const x0 = 0, x1 = W, yb = H, ph = 200 * U, lo = ST.min - (ST.max - ST.min) * 0.15, hi = ST.max + (ST.max - ST.min) * 0.05;
  const X = km => x0 + (x1 - x0) * km / ST.km, Yp = e => yb - ph * (e - lo) / (hi - lo);
  const stepPx = Math.max(1, Math.floor(TR.length / 400));
  c.save(); c.globalAlpha = a;
  const area = k1 => { c.beginPath(); c.moveTo(X(0), yb); for (let k = 0; k <= k1; k += stepPx) c.lineTo(X(TR[k][3]), Yp(TR[k][2])); c.lineTo(X(TR[k1][3]), Yp(TR[k1][2])); c.lineTo(X(TR[k1][3]), yb); c.closePath(); };
  const g = c.createLinearGradient(0, yb - ph, 0, yb); g.addColorStop(0, 'rgba(255,255,255,.55)'); g.addColorStop(1, 'rgba(255,255,255,.12)');
  c.fillStyle = g; area(TR.length - 1); c.fill();
  const n = Math.min(TR.length - 1, Math.floor(d / STEP));
  if (n > 0) { const gy = c.createLinearGradient(0, yb - ph, 0, yb); gy.addColorStop(0, 'rgba(242,238,58,.75)'); gy.addColorStop(1, 'rgba(242,238,58,.15)'); c.fillStyle = gy; area(n); c.fill(); }
  const e = at(d); c.strokeStyle = '#fff'; c.lineWidth = 2 * U; c.setLineDash([6 * U, 6 * U]); c.beginPath(); c.moveTo(X(d), yb); c.lineTo(X(d), Yp(e[2]) - 18 * U); c.stroke(); c.setLineDash([]);
  c.fillStyle = Y; c.beginPath(); c.arc(X(d), Yp(e[2]), 9 * U, 0, 7); c.fill(); c.strokeStyle = '#fff'; c.lineWidth = 3 * U; c.stroke();
  const km = TR.reduce((b, p) => p[2] > b[2] ? p : b, TR[0]);              // 最高点
  shadowText(`最高 ${fmt(ST.max)}m`, clamp(X(km[3]), 120 * U, W - 120 * U), Yp(km[2]) - 16 * U, FONT('MM-Bold', 28), '#fff', 'center');
  c.restore();
}

function drawFollowHud(t, d, a) {
  if (a <= 0) return; const e = at(d);
  c.save(); c.globalAlpha = a;
  drawMinimap(d, 1, 46 * U, 70 * U);
  shadowText('里程 km', 300 * U, 128 * U, FONT('MM-Black', 40), Y);
  numText(d.toFixed(ST.km >= 100 ? 1 : 2), 300 * U, 236 * U, 112);
  const yb = H - 290 * U;
  shadowText('海拔', 48 * U, yb - 96 * U, FONT('MM-Bold', 30), '#fff');
  numText(`${fmt(e[2])} m`, 48 * U, yb - 20 * U, 76);
  shadowText('累计爬升', W - 48 * U, yb - 96 * U, FONT('MM-Bold', 30), '#fff', 'right');
  numText(`+${fmt(e[4])} m`, W - 52 * U, yb - 20 * U, 76, Y, 'right');
  c.restore();
  drawProfile(d, a);
}

function drawTitle(t, a, y) {
  if (a <= 0 || !TL.title) return;
  c.save(); c.globalAlpha = a; const k = E.out(a);
  c.font = FONT('MM-Black', 92); const ts = 92 * Math.min(1, (W - 100 * U) / c.measureText(TL.title).width);   // 长标题缩字号
  shadowText(TL.title, W / 2, y + (1 - k) * 30 * U, FONT('MM-Black', ts), '#fff', 'center', 22);
  if (TL.sub) shadowText(TL.sub, W / 2, y + 70 * U + (1 - k) * 30 * U, FONT('MM-Bold', 38), 'rgba(255,255,255,.92)', 'center');
  c.restore();
}

function drawStats(t, a) {
  if (a <= 0) return; const k = E.out((t - PH.f1 - 1.6) / 1.6);
  const items = [['总里程', ST.km >= 100 ? fmt(ST.km) : ST.km.toFixed(1), 'km'], ['累计爬升', fmt(ST.gain * k), 'm'], ['最高海拔', fmt(ST.max * (0.85 + 0.15 * k)), 'm']];
  const cw = (W - 96 * U) / 3, y = H - 300 * U;
  c.save(); c.globalAlpha = a;
  c.fillStyle = 'rgba(8,10,14,.55)'; c.beginPath(); c.roundRect(48 * U, y - 40 * U, W - 96 * U, 230 * U, 26 * U); c.fill();
  items.forEach(([lab, v, unit], i) => {
    const cx = 48 * U + cw * (i + 0.5);
    shadowText(lab, cx, y + 26 * U, FONT('MM-Bold', 30), 'rgba(255,255,255,.85)', 'center', 6);
    c.font = `${84 * U}px "MM-Num"`; const w = c.measureText(v).width; numText(v, cx - 14 * U, y + 136 * U, 84, Y, 'center');
    shadowText(unit, cx - 14 * U + w / 2 + 8 * U, y + 136 * U, FONT('MM-Bold', 30), '#fff', 'left', 6);
  });
  c.restore();
}

function drawPlace(t) {                                                   // 单点模式：落点脉冲 + 底部地名卡（坐标、海拔）
  const P = TL.place; if (!P) return;
  const a = fade(t, PH.dive - 0.6, null, 0.8); if (a <= 0) return;
  const p = proj(P.at); c.save(); c.globalAlpha = a;
  for (const k of [0, 0.5]) { const q = (t * 0.8 + k) % 1; c.strokeStyle = Y; c.globalAlpha = a * (1 - q); c.lineWidth = 5 * U; c.beginPath(); c.arc(p[0], p[1], (14 + 70 * q) * U, 0, 7); c.stroke(); }
  c.globalAlpha = a; c.fillStyle = '#fff'; c.beginPath(); c.arc(p[0], p[1], 14 * U, 0, 7); c.fill(); c.fillStyle = Y; c.beginPath(); c.arc(p[0], p[1], 9 * U, 0, 7); c.fill();
  const k = E.out(clamp((t - PH.dive) / 0.9)), y = H - 330 * U + (1 - k) * 60 * U; c.globalAlpha = a * k;
  const dm = (v, pos, neg) => { const x = Math.abs(v), d = Math.floor(x), m = Math.floor((x - d) * 60), s2 = Math.round(((x - d) * 60 - m) * 600) / 10; return `${d}°${String(m).padStart(2, '0')}′${s2.toFixed(1).padStart(4, '0')}″${v >= 0 ? pos : neg}`; };
  shadowText(P.name, 64 * U, y, FONT('MM-Black', 84), '#fff', 'left', 20);
  shadowText(`${dm(P.at[1], 'N', 'S')}   ${dm(P.at[0], 'E', 'W')}`, 66 * U, y + 70 * U, `${36 * U}px "MM-Num"`, 'rgba(255,255,255,.9)');
  shadowText('海拔', 66 * U, y + 150 * U, FONT('MM-Bold', 30), '#fff'); numText(`${fmt(P.ele * clamp((t - PH.dive) / 1.6))} m`, 140 * U, y + 156 * U, 72);
  c.restore();
}

function shade(y0, y1, a) {
  if (a <= 0) return; const g = c.createLinearGradient(0, y0, 0, y1); g.addColorStop(0, `rgba(0,0,0,${a})`); g.addColorStop(0.55, `rgba(0,0,0,${a * 0.45})`); g.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = g; c.fillRect(0, Math.min(y0, y1), W, Math.abs(y1 - y0));
}

window.renderFrame = t => {
  const sk = clamp((F[2] - 4) / 3);                                       // 天空自己画：MapLibre 的天空在地球/地形切换后常出不来，露出黑底
  const g = c.createLinearGradient(0, 0, 0, H * 0.6);
  g.addColorStop(0, `rgb(${lerp(0, 74, sk)},${lerp(0, 124, sk)},${lerp(0, 196, sk)})`); g.addColorStop(1, `rgb(${lerp(0, 214, sk)},${lerp(0, 228, sk)},${lerp(0, 240, sk)})`);
  c.fillStyle = g; c.fillRect(0, 0, W, H); c.drawImage(map.getCanvas(), 0, 0, W, H);
  if (F[2] < 6) window.__qaSkipBlack = true;                              // 太空本来就是黑的
  const d = F[5], hudA = fade(t, PH.f0 - 0.4, PH.f1 + 0.9, 0.6, 0.6), topA = Math.max(hudA, fade(t, PH.dive - 1.0, PH.f0 - 0.4, 0.8, 0.6), fade(t, PH.f1 + 1.0, null, 0.8));
  shade(0, 520 * U, topA * 0.62); shade(H, H - 620 * U, Math.max(hudA, fade(t, PH.f1 + 1.4, null, 0.7), TL.place ? fade(t, PH.dive - 0.6, null, 0.8) : 0) * 0.7);   // 雪山上白字看不清：上下压暗
  drawMarks(t, fade(t, PH.dive - 0.4, null, 0.8));
  drawPhotos(t); drawPlace(t);
  drawHiker(t, d, fade(t, PH.f0 - 0.8, null, 0.6));
  drawTitle(t, fade(t, PH.dive - 1.0, PH.f0 - 0.4, 0.8, 0.6), 240 * U);
  drawTitle(t, fade(t, PH.f1 + 1.0, null, 0.8), 240 * U);
  drawFollowHud(t, d, hudA);
  drawStats(t, fade(t, PH.f1 + 1.4, null, 0.7));
  c.save(); c.font = FONT('MM-Bold', 17); c.fillStyle = 'rgba(255,255,255,.55)'; c.textAlign = 'right'; c.fillText(TL.attribution, W - 18 * U, H - 14 * U); c.restore();
};

boot().then(() => { window.__ready = true; }, e => { window.__bootFailed = String(e && e.stack || e); });
})();
