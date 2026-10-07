// map-motion 运行时：timeline（compile.py 产出）→ 每一帧画面。
// 坐标一律 GCJ-02 [lng, lat]（高德）。缩放 zoom 用 Web 墨卡托级别，按 512px 瓦片计（≈ 高清屏的高德级别）。
// zoom < 2.6 画正射投影地球，2.6–3.5 地球与平面地图交叉淡化，> 3.5 只画平面（可叠高德瓦片）。
// 对外：window.MM_TIMELINE（render.py 注入）→ window.prepare(t)（异步：等瓦片/图片）→ window.renderFrame(t)。
(() => {
'use strict';
const TL = window.MM_TIMELINE, cv = document.getElementById('c'), c = cv.getContext('2d');
const W = cv.width = TL.width, H = cv.height = TL.height, U = Math.min(W, H) / 1080;
window.__canvas = cv;
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), lerp = (a, b, e) => a + (b - a) * e;
const E = {
  smooth: p => { p = clamp(p); return p * p * p * (p * (6 * p - 15) + 10); },
  inOut: p => { p = clamp(p); return -(Math.cos(Math.PI * p) - 1) / 2; },
  out: p => 1 - Math.pow(1 - clamp(p), 3),
  back: p => { p = clamp(p); const s = 1.7, q = p - 1; return 1 + (s + 1) * q * q * q + s * q * q; },
  linear: p => clamp(p),
};
const rng = s => () => ((s = Math.imul(s ^ (s >>> 15), 0x2c1b3c6d) ^ (s + 0x6d2b79f5)) >>> 0) / 4294967296;

// ================= 样式
const ST = {
  amap:      { tiles: 'amap', bg: '#f5f3ef', ocean: '#a9cbe8', globeOcean: '#5d9ad6', globeLand: '#f4f1e8', land: '#f2efe9', coast: 'rgba(90,110,130,.45)', prov: 'rgba(120,120,140,.35)', route: '#2f7bf6', route2: '#ff6a3d', casing: '#ffffff', glow: 0, text: '#1d2433', halo: 'rgba(255,255,255,.92)', chip: '#ffffff', chipText: '#1d2433', accent: '#ff4d3d', font: 'MM-Bold', dash: 0 },
  'amap-dark': { tiles: 'amap', tileFilter: 'invert(1) hue-rotate(185deg) brightness(.82) contrast(1.05) saturate(.55)', bg: '#0e1726', ocean: '#0d2236', globeOcean: '#0b1d33', globeLand: '#2a3f5c', land: '#1b2535', coast: 'rgba(120,170,220,.5)', prov: 'rgba(120,170,220,.25)', route: '#36e3ff', route2: '#ffcf3d', casing: 'rgba(0,0,0,.35)', glow: 18, text: '#e9f3ff', halo: 'rgba(8,14,26,.85)', chip: 'rgba(14,26,44,.92)', chipText: '#e9f3ff', accent: '#36e3ff', font: 'MM-Bold', dash: 0 },
  satellite: { tiles: 'sat', labels: true, bg: '#0b1420', ocean: '#0f2741', land: '#3d4a33', coast: 'rgba(255,255,255,.35)', prov: 'rgba(255,255,255,.3)', route: '#ffd23d', route2: '#ff5a5a', casing: 'rgba(0,0,0,.45)', glow: 14, text: '#ffffff', halo: 'rgba(0,0,0,.7)', chip: 'rgba(10,14,20,.82)', chipText: '#ffffff', accent: '#ffd23d', font: 'MM-Bold', dash: 0 },
  dark:      { bg: '#070b14', ocean: '#081120', globeOcean: '#0a1a30', globeLand: '#1f3a5c', land: '#131d2e', coast: 'rgba(80,190,255,.55)', prov: 'rgba(80,190,255,.28)', grid: 'rgba(80,160,255,.07)', route: '#38e8ff', route2: '#ff4fd8', casing: 'rgba(0,0,0,0)', glow: 22, text: '#e6f6ff', halo: 'rgba(5,9,18,.85)', chip: 'rgba(10,22,40,.9)', chipText: '#e6f6ff', accent: '#38e8ff', font: 'MM-Bold', dash: 0 },
  light:     { bg: '#f7f7f4', ocean: '#e4eef5', land: '#ffffff', coast: 'rgba(40,50,70,.35)', prov: 'rgba(40,50,70,.18)', route: '#ff5a36', route2: '#2f6bff', casing: '#ffffff', glow: 0, text: '#151a24', halo: 'rgba(247,247,244,.95)', chip: '#151a24', chipText: '#ffffff', accent: '#ff5a36', font: 'MM-Bold', dash: 0 },
  journal:   { bg: '#f3ecdc', paper: true, ocean: 'rgba(150,190,215,.35)', land: 'rgba(240,226,190,.55)', coast: 'rgba(60,45,30,.55)', prov: 'rgba(60,45,30,.3)', provFill: ['#e9b49c', '#b9d3a2', '#f0cf7c', '#c8b6d6', '#a9c7d6', '#dcc29c'], route: '#c0392b', route2: '#2f6fa8', casing: 'rgba(255,255,255,.6)', glow: 0, text: '#2b241c', halo: 'rgba(243,236,220,.9)', chip: '#f7f2e6', chipText: '#2b241c', accent: '#b83a2e', font: 'MM-Hand', dash: [18, 11] },
  'amap-gray':  { tiles: 'amap', tileFilter: 'grayscale(1) contrast(1.08) brightness(1.04)', bg: '#f2f2f2', ocean: '#cfd6dc', globeOcean: '#8d99a6', globeLand: '#f4f4f4', land: '#f4f4f4', coast: 'rgba(60,60,60,.45)', prov: 'rgba(60,60,60,.25)', route: '#ff4d3d', route2: '#2f6bff', casing: '#ffffff', glow: 0, text: '#111', halo: 'rgba(255,255,255,.92)', chip: '#111', chipText: '#ffffff', accent: '#ff4d3d', font: 'MM-Bold', dash: 0 },
  'amap-sepia': { tiles: 'amap', tileFilter: 'sepia(.7) saturate(.85) contrast(.95) brightness(.98)', bg: '#efe4cf', ocean: '#c9bfa5', globeOcean: '#a3967a', globeLand: '#f1e7d2', land: '#f1e7d2', coast: 'rgba(90,65,35,.55)', prov: 'rgba(90,65,35,.3)', route: '#9b2d1f', route2: '#2d4a6b', casing: 'rgba(255,248,235,.8)', glow: 0, text: '#3a2a18', halo: 'rgba(239,228,207,.92)', chip: '#3a2a18', chipText: '#f1e7d2', accent: '#9b2d1f', font: 'MM-Hand', dash: 0 },
  neon:      { bg: '#0d0221', ocean: '#0d0221', globeOcean: '#170a3a', globeLand: '#2a1258', land: '#1a0b3b', coast: 'rgba(255,43,214,.7)', prov: 'rgba(0,240,255,.25)', grid: 'rgba(255,43,214,.06)', route: '#00f0ff', route2: '#ff2bd6', casing: 'rgba(0,0,0,0)', glow: 26, text: '#fdf0ff', halo: 'rgba(13,2,33,.85)', chip: 'rgba(30,8,60,.9)', chipText: '#fdf0ff', accent: '#ff2bd6', font: 'MM-Bold', dash: 0 },
  ink:       { bg: '#f1ecdf', paper: true, ocean: 'rgba(40,40,40,.05)', globeOcean: '#e6e0d0', globeLand: '#bdb7a8', land: 'rgba(30,30,30,.13)', coast: 'rgba(20,20,20,.75)', prov: 'rgba(20,20,20,.28)', route: '#c8312b', route2: '#1f1f1f', casing: 'rgba(241,236,223,.7)', glow: 0, text: '#1b1b1b', halo: 'rgba(241,236,223,.92)', chip: '#1b1b1b', chipText: '#f1ecdf', accent: '#c8312b', font: 'MM-Hand', dash: 0 },
  blueprint: { bg: '#123a6b', ocean: '#123a6b', globeOcean: '#0f3260', globeLand: '#1d4f8a', land: 'rgba(255,255,255,.06)', coast: 'rgba(255,255,255,.8)', prov: 'rgba(255,255,255,.35)', grid: 'rgba(255,255,255,.09)', route: '#ffffff', route2: '#ffd23d', casing: 'rgba(0,0,0,0)', glow: 0, text: '#ffffff', halo: 'rgba(18,58,107,.9)', chip: 'rgba(255,255,255,.95)', chipText: '#123a6b', accent: '#ffd23d', font: 'MM-Bold', dash: [14, 8] },
  vintage:   { bg: '#e8d9b5', paper: true, ocean: '#c9c3a3', land: '#efe3c4', coast: 'rgba(80,55,30,.7)', prov: 'rgba(80,55,30,.3)', route: '#8a2b1e', route2: '#2d4a6b', casing: 'rgba(0,0,0,0)', glow: 0, text: '#3a2a18', halo: 'rgba(232,217,181,.9)', chip: '#3a2a18', chipText: '#efe3c4', accent: '#8a2b1e', font: 'MM-Hand', dash: [4, 9], sepia: true },
};
const S = ST[TL.style] || ST.amap;
const FONT = (w, size) => `${size * U}px "${w}", "PingFang SC", sans-serif`;

// ================= 投影
const TS = 512;
const merc = ([lng, lat]) => { const s = Math.sin(clamp(lat, -85, 85) * Math.PI / 180); return [(lng + 180) / 360, 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)]; };   // 0..1
const unmerc = ([x, y]) => [x * 360 - 180, Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180 / Math.PI];
let CAM;                                   // 当前帧相机 {lng, lat, zoom}
function setCam(cam) {
  const m = merc([cam.lng, cam.lat]), ww = TS * Math.pow(2, cam.zoom);
  CAM = { ...cam, mx: m[0], my: m[1], ww, R: ww / (2 * Math.PI), globe: clamp((3.6 - cam.zoom) / 0.6) };
}
// 平面：经纬度 → 屏幕
const P = ll => { const m = merc(ll); let dx = m[0] - CAM.mx; dx -= Math.round(dx); return [W / 2 + dx * CAM.ww, H / 2 + (m[1] - CAM.my) * CAM.ww]; };
// 地球：经纬度 → 屏幕（背面返回 null 或贴到地平圈）
const G = (ll, clampLimb) => {
  const d = Math.PI / 180, l = (ll[0] - CAM.lng) * d, f = ll[1] * d, f0 = CAM.lat * d;
  const cc = Math.sin(f0) * Math.sin(f) + Math.cos(f0) * Math.cos(f) * Math.cos(l);
  let x = Math.cos(f) * Math.sin(l), y = Math.cos(f0) * Math.sin(f) - Math.sin(f0) * Math.cos(f) * Math.cos(l);
  if (cc < 0) { if (!clampLimb) return null; const n = Math.hypot(x, y) || 1; x /= n; y /= n; }
  return [W / 2 + x * CAM.R, H / 2 - y * CAM.R];
};
// 图层统一用这个：按当前混合比选投影（地球阶段用 G，平面阶段用 P；交叉淡化时由调用方各画一遍）
let PROJ = P;

// ================= 资源：字体、底图数据、瓦片、图片
const ASSET = {}, IMG = {}, TILE = {};
async function boot() {
  const fonts = [['MM-Bold', 'NotoSansSC-700'], ['MM-Black', 'NotoSansSC-900'], ['MM-Hand', 'LXGWWenKai-500'], ['MM-Num', 'Anton-400']];
  for (const [fam, f] of fonts) { const ff = new FontFace(fam, `url(/asset/fonts/${f}.woff)`); await ff.load(); document.fonts.add(ff); }
  ASSET.land = await (await fetch('/asset/land.json')).json();
  ASSET.china = await (await fetch('/asset/china.json')).json();
  const imgs = new Set(); for (const L of TL.layers) if (L.image) imgs.add(L.image);
  await Promise.all([...imgs].map(u => new Promise((res, rej) => { const im = new Image(); im.onload = () => { IMG[u] = im; res(); }; im.onerror = () => rej(new Error('图片加载失败 ' + u)); im.src = u; })));
  if (S.paper) ASSET.paper = paperTile(S.bg);
  ASSET.globe = await globeTexture();
  window.__total = TL.duration; window.__fps = TL.fps; window.__ready = true;
}
function tileSources() {
  if (!S.tiles) return [];
  if (S.tiles === 'sat') return [{ src: 'sat', ts: 256, off: 1, max: 18 }].concat(S.labels ? [{ src: 'lbl', ts: 512, off: 0, max: 18 }] : []);
  return [{ src: 'amap', ts: 512, off: 0, max: 18 }];
}
function tilesFor(cam) {
  const out = [];
  for (const s of tileSources()) {
    const z = clamp(Math.round(cam.zoom) + s.off, 1, s.max), n = Math.pow(2, z), size = TS * Math.pow(2, cam.zoom) / n;
    const x0 = Math.floor((CAM.mx * CAM.ww - W / 2) / size), x1 = Math.floor((CAM.mx * CAM.ww + W / 2) / size);
    const y0 = Math.max(0, Math.floor((CAM.my * CAM.ww - H / 2) / size)), y1 = Math.min(n - 1, Math.floor((CAM.my * CAM.ww + H / 2) / size));
    for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) out.push({ s, z, x: ((x % n) + n) % n, xs: x, y, size });
  }
  return out;
}
const tileKey = (src, z, x, y) => `${src}/${z}/${x}/${y}`;
function loadTile(src, z, x, y) {
  const k = tileKey(src, z, x, y);
  if (!TILE[k]) TILE[k] = new Promise(res => { const im = new Image(); im.onload = () => { TILE[k].img = im; res(im); }; im.onerror = () => res(null); im.src = `/tile/${k}`; });
  return TILE[k];
}
window.prepare = async t => {
  setCam(camAt(t));
  if (CAM.globe >= 1 || !S.tiles) return;
  const need = tilesFor(CAM);
  await Promise.all(need.map(q => loadTile(q.s.src, q.z, q.x, q.y)));
};

// ================= 相机
function flyInterp(a, b, e) {
  // van Wijk & Nuij「平滑最优缩放平移」，与 Mapbox flyTo 同一公式：远距离先拉远再推近
  const rho = 1.42, ma = merc([a.lng, a.lat]), mb = merc([b.lng, b.lat]);
  let dx = mb[0] - ma[0]; dx -= Math.round(dx); const dy = mb[1] - ma[1];
  const S0 = Math.pow(2, a.zoom), S1 = Math.pow(2, b.zoom), span = Math.max(W, H) / TS;
  const w0 = span / S0, w1 = span / S1, u1 = Math.hypot(dx, dy);
  let wAt, uAt, Stot;
  if (u1 < 1e-9) { const k = w1 < w0 ? -1 : 1; Stot = Math.abs(Math.log(w1 / w0)) / rho; wAt = s => w0 * Math.exp(k * rho * s); uAt = () => 0; }
  else {
    const bb = i => { const wi = i ? w1 : w0; return (w1 * w1 - w0 * w0 + (i ? -1 : 1) * rho ** 4 * u1 * u1) / (2 * wi * rho * rho * u1); };
    const r = i => Math.log(Math.sqrt(bb(i) ** 2 + 1) - bb(i)), r0 = r(0), r1 = r(1);
    Stot = (r1 - r0) / rho;
    wAt = s => w0 * Math.cosh(r0) / Math.cosh(r0 + rho * s);
    uAt = s => w0 * (Math.cosh(r0) * Math.tanh(r0 + rho * s) - Math.sinh(r0)) / (rho * rho) / u1;
  }
  const s = e * Stot, u = clamp(uAt(s), 0, 1), w = wAt(s);
  const m = [ma[0] + dx * u, ma[1] + dy * u], ll = unmerc([((m[0] % 1) + 1) % 1, m[1]]);
  return { lng: ll[0], lat: ll[1], zoom: a.zoom + Math.log2(w0 / w) };
}
function camAt(t) {
  const K = TL.camera; if (t <= K[0].t) return K[0];
  for (let i = 1; i < K.length; i++) {
    const a = K[i - 1], b = K[i]; if (t > b.t) continue;
    const p = (t - a.t) / Math.max(1e-6, b.t - a.t), mode = b.ease || 'smooth';
    if (mode === 'fly') return flyInterp(a, b, E.inOut(p));
    if (mode === 'globe') {                          // 地球段：经度绕着转、缩放线性（级别本身就是对数）
      const e = E.inOut(p); let dl = b.lng - a.lng; dl -= 360 * Math.round(dl / 360);
      return { lng: a.lng + dl * e, lat: lerp(a.lat, b.lat, e), zoom: lerp(a.zoom, b.zoom, E.smooth(p)) };
    }
    const e = (E[mode] || E.inOut)(p), ma = merc([a.lng, a.lat]), mb = merc([b.lng, b.lat]); let dx = mb[0] - ma[0]; dx -= Math.round(dx);
    const ll = unmerc([ma[0] + dx * e, lerp(ma[1], mb[1], e)]);
    return { lng: ll[0], lat: ll[1], zoom: lerp(a.zoom, b.zoom, e) };
  }
  return K[K.length - 1];
}

// ================= 底图
function paperTile(base) {
  const cv2 = document.createElement('canvas'); cv2.width = cv2.height = 512; const g = cv2.getContext('2d'), r = rng(7);
  g.fillStyle = base; g.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 9000; i++) { g.fillStyle = `rgba(90,70,40,${r() * 0.05})`; g.fillRect(r() * 512, r() * 512, 1 + r() * 2, 1 + r() * 2); }
  for (let i = 0; i < 260; i++) { const x = r() * 512, y = r() * 512, a = r() * 3.14, l = 4 + r() * 14; g.strokeStyle = `rgba(110,90,60,${0.05 + r() * 0.07})`; g.lineWidth = 0.7; g.beginPath(); g.moveTo(x, y); g.lineTo(x + Math.cos(a) * l, y + Math.sin(a) * l); g.stroke(); }
  return cv2;
}
function background() {
  if (S.paper) { c.fillStyle = c.createPattern(ASSET.paper, 'repeat'); c.fillRect(0, 0, W, H); } else { c.fillStyle = S.bg; c.fillRect(0, 0, W, H); }
  if (S.grid) { c.save(); c.strokeStyle = S.grid; c.lineWidth = 1; for (let x = 0; x < W; x += 60 * U) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, H); c.stroke(); } for (let y = 0; y < H; y += 60 * U) { c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke(); } c.restore(); }
}
// 平面投影一整条线/环：只给第一个点做 ±180° 归位，之后按经度差连续累加——同一个环永远落在同一份世界副本上，
// 不会在屏幕两侧之间来回跳（逐点归位会画出横穿全屏的线）
function Pline(r) {
  const out = []; let px = null, mx0 = null;
  for (const ll of r) { const m = merc(ll);
    if (px == null) { let dx = m[0] - CAM.mx; dx -= Math.round(dx); px = dx; } else { let d = m[0] - mx0; d -= Math.round(d); px += d; }
    mx0 = m[0]; out.push([W / 2 + px * CAM.ww, H / 2 + (m[1] - CAM.my) * CAM.ww]); }
  return out;
}
// Sutherland–Hodgman：按屏幕外扩一圈的框裁多边形。推得很近时顶点在几十万像素外，画布对超大坐标的填充会破成楔形
function clipRing(pts) {
  const B = [-W, -H, 2 * W, 2 * H];
  if (pts.every(p => p[0] > B[0] && p[0] < B[2] && p[1] > B[1] && p[1] < B[3])) return pts;
  const edges = [[0, B[0], 1], [0, B[2], -1], [1, B[1], 1], [1, B[3], -1]];
  let out = pts;
  for (const [ax, v, sg] of edges) {
    const inp = out; out = []; if (!inp.length) break;
    for (let i = 0; i < inp.length; i++) { const a = inp[i], b = inp[(i + 1) % inp.length], ia = (a[ax] - v) * sg >= 0, ib = (b[ax] - v) * sg >= 0;
      if (ia) out.push(a);
      if (ia !== ib) { const f = (v - a[ax]) / (b[ax] - a[ax]); out.push([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]); } }
  }
  return out;
}
function polyPath(rings, proj, limb) {
  c.beginPath();
  for (const r of rings) {
    if (proj === P) { const pts = clipRing(Pline(r)); pts.forEach((p, i) => i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1])); c.closePath(); continue; }
    let started = false;
    for (const ll of r) { const p = proj(ll, limb); if (!p) { started = false; continue; } started ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]); started = true; }
    if (limb) c.closePath(); }
}
function drawFlat(t) {
  // 平面：矢量陆地＋省界，或高德瓦片
  if (S.tiles) { drawTiles(); }
  else {
    c.fillStyle = S.ocean; c.fillRect(0, 0, W, H);
    c.save(); polyPath(ASSET.land, P); c.fillStyle = S.land; c.fill(); c.strokeStyle = S.coast; c.lineWidth = 1.6 * U; c.stroke(); c.restore();
    drawChina(P, false);
  }
}
function drawChina(proj, limb) {
  const zoom = CAM.zoom;
  c.save();
  ASSET.china.provinces.forEach((p, i) => {
    polyPath(p.rings, proj, limb);
    if (S.provFill) { c.fillStyle = S.provFill[i % S.provFill.length]; c.globalAlpha = 0.45; c.fill(); c.globalAlpha = 1; }
    c.strokeStyle = S.prov; c.lineWidth = (zoom > 5 ? 2 : 1.2) * U; if (S.dash) c.setLineDash([6 * U, 5 * U]); c.stroke(); c.setLineDash([]);
  });
  if (!limb) { c.fillStyle = S.coast; for (const poly of ASSET.china.jd) { polyPath(poly, proj, false); c.fill(); } }   // 九段线：每一段是一个细长小多边形
  c.restore();
}
function drawTiles() {
  c.fillStyle = S.bg; c.fillRect(0, 0, W, H);
  c.save(); if (S.tileFilter) c.filter = S.tileFilter;
  for (const q of tilesFor(CAM)) {
    const k = TILE[tileKey(q.s.src, q.z, q.x, q.y)], im = k && k.img;
    const px = W / 2 + q.xs * q.size - CAM.mx * CAM.ww, py = H / 2 + q.y * q.size - CAM.my * CAM.ww;
    if (im) c.drawImage(im, px, py, q.size + 0.5, q.size + 0.5);
    else for (let up = 1; up <= 5; up++) {                            // 没取到：拿上级瓦片放大顶上
      const z = q.z - up, f = Math.pow(2, up), pk = TILE[tileKey(q.s.src, z, Math.floor(q.x / f), Math.floor(q.y / f))];
      if (pk && pk.img) { const sw = pk.img.width / f; c.drawImage(pk.img, (q.x % f) * sw, (q.y % f) * sw, sw, sw, px, py, q.size + 0.5, q.size + 0.5); break; }
    }
  }
  c.restore();
}
// 地球填色：逐像素反投影取纹理（正射投影下多边形裁剪易破，逐像素最稳）。
// 卫星样式用高德卫星瓦片 z=3 拼成的墨卡托纹理（真实地表）；其它样式把陆地矢量画进等经纬度纹理。
async function globeTexture() {
  const TW = 4096, TH = S.tiles === 'sat' ? 2048 : 2048, cv2 = document.createElement('canvas'); cv2.width = TW; cv2.height = TH; const g = cv2.getContext('2d');
  if (S.tiles === 'sat') {
    const n = 8, ims = await Promise.all([...Array(n * n)].map((_, i) => loadTile('sat', 3, i % n, Math.floor(i / n))));
    g.fillStyle = '#0b1e33'; g.fillRect(0, 0, TW, TH);
    ims.forEach((im, i) => im && g.drawImage(im, (i % n) * TW / n, Math.floor(i / n) * TH / n, TW / n + 1, TH / n + 1));
    return { cv: cv2, data: g.getImageData(0, 0, TW, TH).data, TW, TH, merc: true };
  }
  g.fillStyle = S.globeOcean || S.ocean; g.fillRect(0, 0, TW, TH);
  const X = lng => (lng + 180) / 360 * TW, Y = lat => (90 - lat) / 180 * TH;
  // 环先按经度连续展开（跨 180° 的岛不会拉出横贯全图的线），越界的部分平移 ±360° 再画一遍
  const ringPath = (r, off) => r.forEach(([lng, lat], i) => i ? g.lineTo(X(lng + off), Y(lat)) : g.moveTo(X(lng + off), Y(lat)));
  const unwrap = r => { const o = [r[0].slice()]; for (let i = 1; i < r.length; i++) { let l = r[i][0]; while (l - o[i - 1][0] > 180) l -= 360; while (l - o[i - 1][0] < -180) l += 360; o.push([l, r[i][1]]); } return o; };
  g.fillStyle = S.globeLand || S.land;
  for (const r0 of ASSET.land) { const r = unwrap(r0), mn = Math.min(...r.map(p => p[0])), mx = Math.max(...r.map(p => p[0]));
    if (r0.some(p => p[1] < -60) && mx - mn > 300) { g.beginPath(); ringPath(r, 0); g.lineTo(X(mx), TH); g.lineTo(X(mn), TH); g.closePath(); g.fill(); continue; }   // 南极：环绕极点，往下封到图底
    for (const off of [0, mx > 180 ? -360 : 0, mn < -180 ? 360 : 0].filter((v, i, a) => i === 0 || v !== 0)) { g.beginPath(); ringPath(r, off); g.closePath(); g.fill(); } }
  if (S.provFill) ASSET.china.provinces.forEach((p, i) => { g.beginPath(); for (const r of p.rings) r.forEach(([lng, lat], k) => k ? g.lineTo(X(lng), Y(lat)) : g.moveTo(X(lng), Y(lat))); g.fillStyle = S.provFill[i % S.provFill.length]; g.globalAlpha = 0.5; g.fill(); g.globalAlpha = 1; });
  return { cv: cv2, data: g.getImageData(0, 0, TW, TH).data, TW, TH, merc: false };
}
let GBUF = null;
function globeFill() {
  const T = ASSET.globe, R = CAM.R, cx = W / 2, cy = H / 2, d = Math.PI / 180, f0 = CAM.lat * d, l0 = CAM.lng * d, sf0 = Math.sin(f0), cf0 = Math.cos(f0);
  const x0 = Math.max(0, Math.floor(cx - R)), x1 = Math.min(W, Math.ceil(cx + R)), y0 = Math.max(0, Math.floor(cy - R)), y1 = Math.min(H, Math.ceil(cy + R));
  if (x1 <= x0 || y1 <= y0) return;
  if (!GBUF) GBUF = c.createImageData(W, H);
  const out = GBUF.data; out.fill(0);
  const src = T.data, TW = T.TW, TH = T.TH;
  for (let py = y0; py < y1; py++) { const y = (cy - py - 0.5) / R;
    for (let px = x0; px < x1; px++) { const x = (px + 0.5 - cx) / R, rho2 = x * x + y * y; if (rho2 >= 1) continue;
      const rho = Math.sqrt(rho2), cc = Math.sqrt(1 - rho2);                       // cos c（c = asin ρ）
      const lat = Math.asin(cc * sf0 + (rho ? y * cf0 : 0)), lng = l0 + Math.atan2(x, cc * cf0 - y * sf0);
      let u = ((lng / d + 180) / 360) % 1; if (u < 0) u += 1;
      let v; if (T.merc) { const s = Math.sin(lat); v = 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI); v = Math.min(0.9999, Math.max(0, v)); } else v = (90 - lat / d) / 180;
      const si = ((Math.min(TH - 1, (v * TH) | 0)) * TW + ((u * TW) | 0)) * 4, oi = (py * W + px) * 4;
      out[oi] = src[si]; out[oi + 1] = src[si + 1]; out[oi + 2] = src[si + 2]; out[oi + 3] = 255; } }
  GTMP = GTMP || Object.assign(document.createElement('canvas'), { width: W, height: H });
  GTMP.getContext('2d').putImageData(GBUF, 0, 0, x0, y0, x1 - x0, y1 - y0);
  c.drawImage(GTMP, 0, 0);
}
let GTMP = null;
function drawGlobe(t, alpha) {
  if (alpha <= 0) return;
  c.save(); c.globalAlpha = alpha;
  const R = CAM.R, cx = W / 2, cy = H / 2;
  const glow = c.createRadialGradient(cx, cy, R * 0.9, cx, cy, R * 1.25); glow.addColorStop(0, S.glow ? 'rgba(80,190,255,.22)' : 'rgba(120,170,220,.25)'); glow.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = glow; c.beginPath(); c.arc(cx, cy, R * 1.25, 0, 7); c.fill();
  globeFill();
  c.save(); c.beginPath(); c.arc(cx, cy, R, 0, 7); c.clip();
  // 经纬网
  c.strokeStyle = S.glow ? 'rgba(80,190,255,.18)' : 'rgba(255,255,255,.25)'; c.lineWidth = 1 * U;
  for (let lng = -180; lng < 180; lng += 20) { c.beginPath(); let s = false; for (let lat = -88; lat <= 88; lat += 4) { const p = G([lng, lat]); if (!p) { s = false; continue; } s ? c.lineTo(...p) : c.moveTo(...p); s = true; } c.stroke(); }
  for (let lat = -60; lat <= 60; lat += 20) { c.beginPath(); let s = false; for (let lng = -180; lng <= 180; lng += 4) { const p = G([lng, lat]); if (!p) { s = false; continue; } s ? c.lineTo(...p) : c.moveTo(...p); s = true; } c.stroke(); }
  // 海岸线只描线（填色已由逐像素完成）：背面的点断开，不贴地平圈
  if (S.tiles !== 'sat') { c.strokeStyle = S.coast; c.lineWidth = 1.2 * U; for (const r of ASSET.land) { if (!r.some(ll => G(ll))) continue; polyPath([r], G, false); c.stroke(); } }
  drawChina(G, false);
  // 明暗：左上亮右下暗
  const sh = c.createRadialGradient(cx - R * 0.4, cy - R * 0.45, R * 0.2, cx, cy, R * 1.05); sh.addColorStop(0, S.glow ? 'rgba(255,255,255,.04)' : 'rgba(255,255,255,.12)');   // 暗色样式高光要轻，不然整球发雾 sh.addColorStop(0.7, 'rgba(0,0,0,0)'); sh.addColorStop(1, 'rgba(0,0,20,.35)');
  c.fillStyle = sh; c.fillRect(cx - R, cy - R, 2 * R, 2 * R);
  c.restore(); c.restore();
}
function shade(hex, k) { if (!hex.startsWith('#')) return hex; const n = parseInt(hex.slice(1), 16), f = v => clamp(Math.round(v * (1 + k)), 0, 255); return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`; }

// ================= 图层
const on = (L, t) => t >= L.t0 && t < (L.t_end ?? Infinity);
function screenLine(line) { return PROJ === P ? Pline(line) : line.map(ll => PROJ(ll)).filter(Boolean); }
function cumLen(pts) { const L = [0]; for (let i = 1; i < pts.length; i++) L.push(L[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])); return L; }
function pointAt(pts, cum, d) { if (pts.length < 2) return [pts[0] || [0, 0], 0]; d = clamp(d, 0, cum[cum.length - 1]); let i = 1; while (i < cum.length - 1 && cum[i] < d) i++; const f = (d - cum[i - 1]) / Math.max(1e-9, cum[i] - cum[i - 1]);
  return [[lerp(pts[i - 1][0], pts[i][0], f), lerp(pts[i - 1][1], pts[i][1], f)], Math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])]; }
function partial(pts, cum, d) { const out = []; for (let i = 0; i < pts.length; i++) { if (cum[i] <= d) out.push(pts[i]); else { out.push(pointAt(pts, cum, d)[0]); break; } } return out; }
function stroke(pts, col, w, { dash, glow, casing } = {}) {
  if (pts.length < 2) return;
  const path = () => { c.beginPath(); pts.forEach((p, i) => i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1])); };
  c.save(); c.lineCap = 'round'; c.lineJoin = 'round';
  if (casing) { path(); c.strokeStyle = casing; c.lineWidth = w + 6 * U; c.stroke(); }
  if (glow) { c.shadowColor = col; c.shadowBlur = glow * U; }
  if (dash) c.setLineDash(dash.map(v => v * U));
  path(); c.strokeStyle = col; c.lineWidth = w; c.stroke();
  if (glow) { c.shadowBlur = 0; c.setLineDash([]); path(); c.strokeStyle = 'rgba(255,255,255,.75)'; c.lineWidth = w * 0.35; c.stroke(); }
  c.restore();
}
// 飞线：大圆插值后在屏幕上往法线方向拱起
function arcPts(L) {
  const a = PROJ(L.from), b = PROJ(L.to); if (!a || !b) return [];
  const pts = screenLine(L.line); if (pts.length < 2) return [];
  const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy), nx = -dy / (len || 1), ny = dx / (len || 1), h = (L.height ?? 0.22) * len * (nx * 0 + 1);
  const sgn = ny > 0 ? -1 : 1;                                        // 永远往屏幕上方拱
  return pts.map((p, i) => { const s = i / (pts.length - 1), k = Math.sin(Math.PI * s) * h * sgn; return [p[0] + nx * k, p[1] + ny * k]; });
}
function vehicle(kind, x, y, ang, t, col) {
  c.save(); c.translate(x, y); const s = U * 1.1;
  if (kind === 'plane') {
    c.rotate(ang); c.scale(s, s); c.fillStyle = '#ffffff'; c.strokeStyle = 'rgba(0,0,0,.35)'; c.lineWidth = 2;
    c.beginPath(); c.moveTo(30, 0); c.quadraticCurveTo(26, -4, 14, -4); c.lineTo(2, -26); c.lineTo(-6, -26); c.lineTo(0, -4); c.lineTo(-16, -4); c.lineTo(-22, -13); c.lineTo(-27, -13); c.lineTo(-23, 0);
    c.lineTo(-27, 13); c.lineTo(-22, 13); c.lineTo(-16, 4); c.lineTo(0, 4); c.lineTo(-6, 26); c.lineTo(2, 26); c.lineTo(14, 4); c.quadraticCurveTo(26, 4, 30, 0); c.closePath();
    c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 10; c.shadowOffsetY = 6; c.fill(); c.shadowColor = 'transparent'; c.stroke();
  } else if (kind === 'car' || kind === 'bus') {
    c.rotate(ang); c.scale(s, s); const L2 = kind === 'bus' ? 30 : 22;
    c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 8; c.shadowOffsetY = 4; c.fillStyle = col; rr(-L2, -11, L2 * 2, 22, 7); c.fill(); c.shadowColor = 'transparent';
    c.strokeStyle = 'rgba(0,0,0,.4)'; c.lineWidth = 2; c.stroke(); c.fillStyle = 'rgba(210,235,250,.95)'; rr(L2 - 15, -8, 7, 16, 3); c.fill(); rr(-L2 + 5, -8, 5, 16, 2); c.fill();
    c.fillStyle = '#fff8c8'; c.beginPath(); c.arc(L2 - 2, -6, 2.2, 0, 7); c.arc(L2 - 2, 6, 2.2, 0, 7); c.fill();
  } else if (kind === 'walk' || kind === 'bike' || kind === 'dot') {
    const pulse = (t * 1.6) % 1; c.fillStyle = col; c.globalAlpha = 0.35 * (1 - pulse); c.beginPath(); c.arc(0, 0, (14 + 26 * pulse) * s, 0, 7); c.fill();
    c.globalAlpha = 1; c.fillStyle = '#fff'; c.beginPath(); c.arc(0, 0, 13 * s, 0, 7); c.fill(); c.fillStyle = col; c.beginPath(); c.arc(0, 0, 9 * s, 0, 7); c.fill();
  } else if (kind === 'train') {
    c.rotate(ang); c.scale(s, s); c.fillStyle = '#fff'; c.strokeStyle = col; c.lineWidth = 3; rr(-34, -9, 68, 18, 9); c.fill(); c.stroke(); c.fillStyle = col; rr(-20, -5, 36, 10, 3); c.fill();
  }
  c.restore();
}
function rr(x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }
function chip(text, x, y, { sub, align = 'left', size = 40, big } = {}) {
  c.save(); c.font = FONT(S.font, size); const w = c.measureText(text).width; let sw = 0;
  if (sub) { c.font = FONT('MM-Bold', size * 0.55); sw = c.measureText(sub).width; }
  const pad = 18 * U, bw = Math.max(w, sw) + pad * 2, bh = size * U * (sub ? 1.9 : 1.35);
  const bx = align === 'left' ? x : align === 'right' ? x - bw : x - bw / 2, by = y - bh / 2;
  c.shadowColor = 'rgba(0,0,0,.25)'; c.shadowBlur = 14 * U; c.shadowOffsetY = 5 * U; c.fillStyle = S.chip; rr(bx, by, bw, bh, 12 * U); c.fill(); c.shadowColor = 'transparent';
  if (S.glow) { c.strokeStyle = S.accent; c.globalAlpha = 0.7; c.lineWidth = 2 * U; c.stroke(); c.globalAlpha = 1; }
  c.fillStyle = S.chipText; c.textBaseline = 'middle'; c.font = FONT(S.font, size); c.fillText(text, bx + pad, sub ? by + bh * 0.36 : y);
  if (sub) { c.font = FONT('MM-Bold', size * 0.55); c.globalAlpha = 0.7; c.fillText(sub, bx + pad, by + bh * 0.74); }
  c.restore();
}
function labelText(text, x, y, size = 34, align = 'left') { c.save(); c.font = FONT(S.font, size); c.textAlign = align; c.textBaseline = 'middle'; c.lineJoin = 'round'; c.strokeStyle = S.halo; c.lineWidth = 8 * U; c.strokeText(text, x, y); c.fillStyle = S.text; c.fillText(text, x, y); c.restore(); }
function pin(L, t) {
  const p = PROJ(L.lnglat); if (!p) return; const lt = t - L.t0, [x, y] = p, col = L.color || S.accent;
  const drop = E.back(clamp(lt / 0.55)), yy = y - (1 - drop) * 160 * U, fade = L.t_out != null ? 1 - clamp((t - L.t_out) / 0.3) : 1;
  if (fade <= 0) return; c.save(); c.globalAlpha = fade;
  for (let k = 0; k < 2; k++) { const ph = ((lt - 0.4) * 0.8 + k * 0.5) % 1; if (lt < 0.4) break; c.strokeStyle = col; c.globalAlpha = fade * 0.6 * (1 - ph); c.lineWidth = 3 * U; c.beginPath(); c.ellipse(x, y, (10 + 60 * ph) * U, (5 + 26 * ph) * U, 0, 0, 7); c.stroke(); }
  c.globalAlpha = fade;
  if (L.kind === 'dot' || S.glow) {
    c.shadowColor = col; c.shadowBlur = 20 * U; c.fillStyle = col; c.beginPath(); c.arc(x, yy, 11 * U, 0, 7); c.fill(); c.shadowBlur = 0; c.fillStyle = '#fff'; c.beginPath(); c.arc(x, yy, 5 * U, 0, 7); c.fill();
  } else if (L.kind === 'flag') {                                        // 山顶旗：旗面飘动
    c.save(); c.translate(x, yy); c.scale(U, U); c.strokeStyle = '#2b2b2b'; c.lineWidth = 4; c.beginPath(); c.moveTo(0, 0); c.lineTo(0, -78); c.stroke();
    c.fillStyle = col; c.beginPath(); c.moveTo(0, -78); for (let i = 0; i <= 10; i++) { const u = i / 10; c.lineTo(u * 52, -78 + Math.sin(u * 5 + t * 7) * 4 * u); } for (let i = 10; i >= 0; i--) { const u = i / 10; c.lineTo(u * 52, -48 + Math.sin(u * 5 + t * 7) * 4 * u); } c.closePath(); c.fill();
    c.fillStyle = 'rgba(0,0,0,.3)'; c.beginPath(); c.ellipse(0, 2, 12, 4, 0, 0, 7); c.fill(); c.restore();
  } else if (L.kind === 'stamp' || S.font === 'MM-Hand') {
    const sc = lt < 0.5 ? 1 + 0.6 * (1 - E.out(lt / 0.5)) : 1; c.save(); c.translate(x + 40 * U, y + 30 * U); c.rotate(-0.2); c.scale(sc * U, sc * U);
    c.globalAlpha = fade * clamp(lt / 0.12) * 0.85; c.strokeStyle = col; c.fillStyle = col; c.lineWidth = 4; c.beginPath(); c.arc(0, 0, 44, 0, 7); c.stroke(); c.lineWidth = 2; c.beginPath(); c.arc(0, 0, 36, 0, 7); c.stroke();
    c.font = `${(L.label || '').length > 3 ? 18 : 24}px "MM-Black"`; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText((L.label || '').slice(0, 5), 0, -4); c.font = '13px "MM-Num"'; c.fillText(L.stampSub || '', 0, 18); c.restore();
    c.fillStyle = col; c.beginPath(); c.arc(x, y, 8 * U, 0, 7); c.fill();
  } else {
    c.save(); c.translate(x, yy); c.scale(U, U); c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 10; c.shadowOffsetY = 6;
    c.fillStyle = col; c.beginPath(); c.moveTo(0, 0); c.bezierCurveTo(-6, -14, -22, -24, -22, -44); c.arc(0, -44, 22, Math.PI, 0); c.bezierCurveTo(22, -24, 6, -14, 0, 0); c.fill();
    c.shadowColor = 'transparent'; c.fillStyle = '#fff'; c.beginPath(); c.arc(0, -44, 8.5, 0, 7); c.fill(); c.restore();
  }
  const lo = L.label_out != null ? 1 - clamp((t - L.label_out) / 0.35) : 1;
  if (L.label && lt > 0.35 && lo > 0) { const a = clamp((lt - 0.35) / 0.3) * lo; c.globalAlpha = fade * a;
    if (L.chip) chip(L.label, x + 30 * U, yy - (L.kind === 'dot' || S.glow ? 0 : 44 * U), { sub: L.sub, size: L.size || 40 });
    else labelText(L.label, x + 22 * U, yy - (S.glow || L.kind === 'dot' ? 0 : 50 * U), L.size || 38); }
  c.restore();
}
function route(L, t) {
  const fade = L.t_out != null ? 1 - clamp((t - L.t_out) / 0.4) : 1; if (fade <= 0) return;
  const pts = L.arc ? arcPts(L) : screenLine(L.line); if (pts.length < 2) return;
  const cum = cumLen(pts), tot = cum[cum.length - 1], p = (E[L.ease || 'inOut'])((t - L.t0) / Math.max(0.01, L.t1 - L.t0)), d = tot * p;
  const col = L.color || (L.second ? S.route2 : S.route), w = (L.width || 7) * U, glow = S.glow;
  c.save(); c.globalAlpha = fade;
  if (L.ghost) stroke(pts, col, w * 0.5, { dash: [6, 10] });                       // 先铺一条淡虚线预告全程
  if (!L.hideLine) stroke(partial(pts, cum, d), col, w, { dash: L.dash ?? (S.dash || null), glow, casing: L.arc ? null : S.casing });
  if (L.vehicle && p > 0 && (p < 1 || L.park)) { const [q, ang] = pointAt(pts, cum, d); vehicle(L.vehicle, q[0], q[1], ang, t, col); }
  else if (!L.vehicle && p > 0 && p < 1) { const [q] = pointAt(pts, cum, d); c.fillStyle = '#fff'; c.shadowColor = col; c.shadowBlur = 16 * U; c.beginPath(); c.arc(q[0], q[1], w * 0.9, 0, 7); c.fill(); }
  c.restore();
}
function region(L, t) {
  const lt = t - L.t0, drawP = E.inOut(lt / (L.draw || 1.2)), fillA = clamp((lt - (L.draw || 1.2) * 0.8) / 0.6) * (L.t_out != null ? 1 - clamp((t - L.t_out) / 0.4) : 1);
  const col = L.color || S.accent;
  c.save();
  if (fillA > 0) { polyPath(L.rings, PROJ, CAM.globe > 0.5); c.fillStyle = col; c.globalAlpha = fillA * (L.opacity ?? 0.38); c.fill('evenodd'); c.globalAlpha = 1; }
  for (const r of L.rings) { const pts = screenLine(r); if (pts.length < 2) continue; const cum = cumLen(pts);
    const big = r.length > 40, d = (big ? drawP : clamp(drawP * 1.5)) * cum[cum.length - 1];
    stroke(partial(pts, cum, d), col, (L.width || 4) * U, { glow: S.glow, dash: S.dash ? [10, 6] : null }); }
  if (L.label && fillA > 0) { const p = PROJ(L.center); if (p) { c.globalAlpha = fillA; labelText(L.label, p[0], p[1] + (L.size || 54) * 0.9 * U, L.size || 54, 'center'); } }   // 写在中心偏下：中心常有落点针
  c.restore();
}
function hudTitle(L, t) {
  const lt = t - L.t0, out = L.t_out != null ? clamp((t - L.t_out) / 0.35) : 0; if (out >= 1) return;
  const a = E.out(lt / 0.5) * (1 - out), pos = L.pos || 'top', y = pos === 'top' ? H * 0.12 : pos === 'center' ? H * 0.45 : H * 0.84;
  c.save(); c.globalAlpha = a; c.translate(0, (1 - E.out(lt / 0.5)) * 30 * U);
  c.textAlign = 'center'; c.textBaseline = 'middle';
  const size = (L.size || (W > H ? 72 : 84)) * U;
  c.font = `${size}px "${S.font === 'MM-Hand' ? 'MM-Hand' : 'MM-Black'}", sans-serif`;
  const tw = c.measureText(L.text).width;
  if (L.plate !== false) { c.fillStyle = S.chip; c.globalAlpha = a * (S.paper ? 0.92 : 0.86); rr(W / 2 - tw / 2 - 40 * U, y - size * 0.85, tw + 80 * U, size * (L.sub ? 2.35 : 1.7), 18 * U); c.fill(); c.globalAlpha = a; }
  c.fillStyle = L.plate === false ? S.text : S.chipText; c.fillText(L.text, W / 2, y);
  if (L.sub) { c.font = FONT('MM-Bold', size * 0.4 / U); c.globalAlpha = a * 0.75; c.fillText(L.sub, W / 2, y + size * 0.85); }
  c.restore();
}
function odometer(L, t) {
  const v = lerp(L.from || 0, L.to, E.inOut((t - L.t0) / Math.max(0.01, L.t1 - L.t0)));
  const x = W - 50 * U, y = (W > H ? 90 : 230) * U, out = L.t_out != null ? clamp((t - L.t_out) / 0.3) : 0; if (out >= 1) return;
  c.save(); c.globalAlpha = (1 - out) * E.out((t - L.t0) / 0.3); c.textAlign = 'right';
  const txt = L.decimals ? v.toFixed(L.decimals) : Math.round(v).toLocaleString('en-US'); c.font = `${96 * U}px "MM-Num"`; const w = c.measureText(txt).width + 120 * U;
  c.fillStyle = S.chip; rr(x - w - 20 * U, y - 90 * U, w + 40 * U, 150 * U, 16 * U); c.fill();
  c.fillStyle = S.chipText; c.fillText(txt, x - 70 * U, y + 30 * U); c.font = `${34 * U}px "MM-Num"`; c.fillText('KM', x - 10 * U, y + 30 * U);
  c.font = FONT('MM-Bold', 26); c.globalAlpha *= 0.7; c.fillText(L.label || '已行驶', x - 10 * U, y - 52 * U); c.restore();
}
function caption(L, t) {
  const out = L.t_out != null ? clamp((t - L.t_out) / 0.3) : 0; if (out >= 1) return;
  const a = E.out((t - L.t0) / 0.35) * (1 - out); c.save(); c.globalAlpha = a; chip(L.text, 50 * U, (W > H ? 90 : 230) * U, { sub: L.sub, size: L.size || 52 }); c.restore();
}
function photo(L, t) {
  const im = IMG[L.image]; if (!im) return; const lt = t - L.t0, out = L.t_out != null ? clamp((t - L.t_out) / 0.35) : 0; if (out >= 1) return;
  const pw = (W > H ? 420 : 460) * U, ph = pw * clamp(im.height / im.width, 0.7, 1.3), fw = pw + 36 * U, fh = ph + 110 * U;
  const slot = L.slot || 0, x = W > H ? W - 330 * U - slot * 60 * U : W / 2 + (slot % 2 ? 200 : -200) * U, y = W > H ? H / 2 + slot * 40 * U : H - 560 * U + (slot % 2 ? 40 : -20) * U;
  const e = E.back(clamp(lt / 0.45)), rot = (slot % 2 ? 0.07 : -0.06);
  c.save(); c.globalAlpha = 1 - out; c.translate(x, y + (1 - e) * 500 * U + out * 120 * U); c.rotate(rot * e + (1 - e) * 0.3);
  c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 18 * U; c.shadowOffsetY = 10 * U; c.fillStyle = '#fbfaf6'; c.fillRect(-fw / 2, -fh / 2, fw, fh); c.shadowColor = 'transparent';
  const sc = Math.max(pw / im.width, ph / im.height); c.save(); c.beginPath(); c.rect(-pw / 2, -fh / 2 + 18 * U, pw, ph); c.clip();
  c.drawImage(im, -im.width * sc / 2, -fh / 2 + 18 * U + ph / 2 - im.height * sc / 2, im.width * sc, im.height * sc); c.restore();
  if (L.caption) { c.font = `${34 * U}px "MM-Hand"`; c.fillStyle = '#2b241c'; c.textAlign = 'center'; c.fillText(L.caption, 0, fh / 2 - 36 * U); }
  c.restore();
}
// 海拔剖面卡：曲线随路线进度画出，读数跟着走
function profile(L, t) {
  const out = L.t_out != null ? clamp((t - L.t_out) / 0.35) : 0; if (out >= 1) return;
  const p = (E[L.ease || 'inOut'])((t - L.t0) / Math.max(0.01, L.t1 - L.t0)), S0 = L.samples, n = S0.length;
  const landscape = W > H, cw = landscape ? 760 * U : W - 100 * U, ch = landscape ? 250 * U : 300 * U, x0 = landscape ? W - cw - 50 * U : 50 * U, y0 = H - ch - (landscape ? 50 : 150) * U;
  const a = E.out((t - L.t0 + 0.3) / 0.4) * (1 - out);
  c.save(); c.globalAlpha = a; c.translate(0, (1 - a) * 40 * U);
  c.fillStyle = S.chip; c.shadowColor = 'rgba(0,0,0,.3)'; c.shadowBlur = 18 * U; rr(x0, y0, cw, ch, 18 * U); c.fill(); c.shadowColor = 'transparent';
  const gx = x0 + 30 * U, gw = cw - 60 * U, gy = y0 + 110 * U, gh = ch - 140 * U;
  const lo = Math.min(...S0.map(s => s[1])), hi = Math.max(...S0.map(s => s[1])), span = Math.max(30, hi - lo);
  const X = i => gx + gw * i / (n - 1), Y = e => gy + gh - (e - lo) / span * gh;
  const k = p * (n - 1), ki = Math.floor(k), kf = k - ki, cur = ki >= n - 1 ? S0[n - 1][1] : lerp(S0[ki][1], S0[ki + 1][1], kf);
  // 全程淡底线（预告地形）＋已走部分实心填充
  c.beginPath(); S0.forEach((s, i) => i ? c.lineTo(X(i), Y(s[1])) : c.moveTo(X(i), Y(s[1]))); c.strokeStyle = S.chipText; c.globalAlpha = a * 0.22; c.lineWidth = 2 * U; c.stroke(); c.globalAlpha = a;
  const grad = c.createLinearGradient(0, gy, 0, gy + gh); grad.addColorStop(0, S.route); grad.addColorStop(1, 'rgba(0,0,0,0)');
  c.beginPath(); c.moveTo(X(0), gy + gh); for (let i = 0; i <= ki && i < n; i++) c.lineTo(X(i), Y(S0[i][1])); if (ki < n - 1) c.lineTo(X(k), Y(cur)); c.lineTo(X(Math.min(k, n - 1)), gy + gh); c.closePath(); c.fillStyle = grad; c.globalAlpha = a * 0.55; c.fill(); c.globalAlpha = a;
  c.beginPath(); for (let i = 0; i <= ki && i < n; i++) i ? c.lineTo(X(i), Y(S0[i][1])) : c.moveTo(X(i), Y(S0[i][1])); if (ki < n - 1) c.lineTo(X(k), Y(cur)); c.strokeStyle = S.route; c.lineWidth = 4 * U; c.stroke();
  c.fillStyle = '#fff'; c.strokeStyle = S.route; c.lineWidth = 3 * U; c.beginPath(); c.arc(X(Math.min(k, n - 1)), Y(cur), 8 * U, 0, 7); c.fill(); c.stroke();
  // 读数
  let gain = 0; for (let i = 1; i <= ki && i < n; i++) gain += Math.max(0, S0[i][1] - S0[i - 1][1]); if (ki < n - 1 && ki >= 0) gain += Math.max(0, cur - S0[ki][1]);
  const km = (L.km || S0[n - 1][0]) * p;
  c.fillStyle = S.chipText; c.textBaseline = 'alphabetic'; c.textAlign = 'left';
  c.font = FONT('MM-Bold', 24); c.globalAlpha = a * 0.65; c.fillText(L.label || '海拔', gx, y0 + 42 * U); c.globalAlpha = a;
  c.font = `${64 * U}px "MM-Num"`; const et = Math.round(cur).toLocaleString('en-US'); c.fillText(et, gx, y0 + 96 * U); const ew = c.measureText(et).width;
  c.font = `${28 * U}px "MM-Num"`; c.fillText('M', gx + ew + 8 * U, y0 + 96 * U);
  c.textAlign = 'right'; c.font = `${44 * U}px "MM-Num"`; c.fillText(`+${Math.round(gain)} M`, x0 + cw - 30 * U, y0 + 96 * U);
  c.font = FONT('MM-Bold', 24); c.globalAlpha = a * 0.65; c.fillText(`累计爬升 · ${km.toFixed(km < 10 ? 2 : 0)} km`, x0 + cw - 30 * U, y0 + 42 * U);
  c.restore();
}
// 瞄准镜：四角框收缩锁定、刻度圈旋转、十字线；锁定那一下闪光
function reticle(L, t) {
  const lt = t - L.t0, lock = L.lock ?? 1.2, e = E.inOut(lt / lock), out = L.t_out != null ? clamp((t - L.t_out) / 0.4) : 0; if (out >= 1) return;
  const cx = W / 2, cy = H / 2, sz = lerp(Math.min(W, H) * 0.42, 110 * U, e), col = L.color || S.accent;
  c.save(); c.globalAlpha = clamp(lt / 0.2) * (1 - out); c.strokeStyle = col; c.lineWidth = 4 * U; c.lineCap = 'square';
  const k = sz * 0.32;
  for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) { c.beginPath(); c.moveTo(cx + sx * sz, cy + sy * (sz - k)); c.lineTo(cx + sx * sz, cy + sy * sz); c.lineTo(cx + sx * (sz - k), cy + sy * sz); c.stroke(); }
  c.lineWidth = 2 * U; c.globalAlpha *= 0.8; c.save(); c.translate(cx, cy); c.rotate(lt * 0.8 * (1 - e) + e * 0.6);
  for (let i = 0; i < 48; i++) { const a = i / 48 * Math.PI * 2, r1 = sz * 0.72, r2 = r1 + (i % 4 ? 8 : 18) * U; c.beginPath(); c.moveTo(Math.cos(a) * r1, Math.sin(a) * r1); c.lineTo(Math.cos(a) * r2, Math.sin(a) * r2); c.stroke(); }
  c.restore();
  c.globalAlpha = clamp(lt / 0.2) * (1 - out) * 0.55; c.setLineDash([10 * U, 10 * U]);
  for (const [x1, y1, x2, y2] of [[0, cy, cx - sz - 20 * U, cy], [cx + sz + 20 * U, cy, W, cy], [cx, 0, cx, cy - sz - 20 * U], [cx, cy + sz + 20 * U, cx, H]]) { c.beginPath(); c.moveTo(x1, y1); c.lineTo(x2, y2); c.stroke(); }
  c.setLineDash([]);
  if (lt > lock) { const f = clamp((lt - lock) / 0.5); c.globalAlpha = (1 - f) * (1 - out); c.fillStyle = col; c.beginPath(); c.arc(cx, cy, sz * (1 + f * 1.4), 0, 7); c.lineWidth = 6 * U * (1 - f); c.stroke();
    c.globalAlpha = (1 - out) * clamp((lt - lock) / 0.15); c.font = `${30 * U}px "MM-Num"`; c.textAlign = 'center'; c.letterSpacing = `${6 * U}px`; c.fillText('LOCKED', cx, cy - sz - 34 * U); }
  c.restore();
}
// 坐标卡：地名打字、经纬度数字滚动、海拔、日期
function dms(v, pos, neg) { const s = v < 0 ? neg : pos; v = Math.abs(v); const d = Math.floor(v), mf = (v - d) * 60, m = Math.floor(mf), sec = (mf - m) * 60; return `${d}°${String(m).padStart(2, '0')}′${sec.toFixed(1).padStart(4, '0')}″${s}`; }
function coordcard(L, t) {
  const lt = t - L.t0, out = L.t_out != null ? clamp((t - L.t_out) / 0.35) : 0; if (out >= 1) return;
  const roll = E.out(lt / 1.1), lat = L.lnglat[1] * roll, lng = L.lnglat[0] * roll, e = E.out(lt / 0.45);
  const landscape = W > H, cw = landscape ? 720 * U : W - 100 * U, x0 = 50 * U, y0 = landscape ? H - 330 * U : H - 470 * U, chh = (L.sub ? 290 : 250) * U;
  c.save(); c.globalAlpha = e * (1 - out); c.translate(-(1 - e) * 80 * U, 0);
  c.fillStyle = S.chip; c.shadowColor = 'rgba(0,0,0,.35)'; c.shadowBlur = 20 * U; rr(x0, y0, cw, chh, 16 * U); c.fill(); c.shadowColor = 'transparent';
  c.fillStyle = L.color || S.accent; c.fillRect(x0, y0 + 24 * U, 8 * U, chh - 48 * U);
  const tx = x0 + 40 * U; c.textAlign = 'left'; c.fillStyle = S.chipText;
  c.font = `${24 * U}px "MM-Num"`; c.letterSpacing = `${5 * U}px`; c.globalAlpha *= 0.65; c.fillText(L.kicker || 'YOU ARE HERE', tx, y0 + 52 * U); c.letterSpacing = '0px'; c.globalAlpha = e * (1 - out);
  const name = L.name || ''; const nc = Math.ceil(clamp((lt - 0.15) / 0.6) * [...name].length);
  c.font = FONT('MM-Black', 68); c.fillText([...name].slice(0, nc).join(''), tx, y0 + 128 * U);
  let y = y0 + 128 * U; if (L.sub) { y += 46 * U; c.font = FONT('MM-Bold', 30); c.globalAlpha *= 0.75; c.fillText(L.sub, tx, y); c.globalAlpha = e * (1 - out); }
  y += 62 * U; c.font = `${38 * U}px "MM-Num"`; c.fillText(`${dms(lat, 'N', 'S')}   ${dms(lng, 'E', 'W')}`, tx, y);
  const bits = []; if (L.alt != null) bits.push(`ALT ${Math.round(L.alt * roll)} M`); if (L.date) bits.push(L.date);
  if (bits.length) { c.font = `${28 * U}px "MM-Num"`; c.globalAlpha *= 0.7; c.fillText(bits.join('   ·   '), tx, y + 44 * U); }
  c.restore();
}
const DRAW = { route, pin, region, title: hudTitle, odometer, caption, photo, profile, reticle, coordcard };
const ORDER = { region: 0, route: 1, pin: 2, reticle: 3, caption: 3, odometer: 3, profile: 3, coordcard: 4, title: 4, photo: 5 };

// ================= 帧
window.renderFrame = t => {
  setCam(camAt(t));
  c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1; background();
  const gA = CAM.globe, fA = 1 - gA;
  const layers = TL.layers.filter(L => on(L, t)).sort((a, b) => (ORDER[a.type] ?? 9) - (ORDER[b.type] ?? 9));
  const mapLayers = layers.filter(L => ['route', 'pin', 'region'].includes(L.type)), hud = layers.filter(L => !['route', 'pin', 'region'].includes(L.type));
  if (fA > 0) { c.save(); c.globalAlpha = fA; drawFlat(t); PROJ = P; for (const L of mapLayers) DRAW[L.type](L, t); c.restore(); }
  if (gA > 0) { drawGlobe(t, gA); PROJ = (ll) => G(ll); c.save(); c.globalAlpha = gA; for (const L of mapLayers) DRAW[L.type](L, t); c.restore(); }
  PROJ = P;
  if (S.sepia) { c.save(); c.globalCompositeOperation = 'multiply'; c.fillStyle = 'rgba(232,210,170,.35)'; c.fillRect(0, 0, W, H); c.restore(); }
  // 暗角
  const vg = c.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.45, W / 2, H / 2, Math.max(W, H) * 0.75); vg.addColorStop(0, 'rgba(0,0,0,0)'); vg.addColorStop(1, S.glow ? 'rgba(0,0,0,.45)' : 'rgba(40,30,20,.18)');
  c.fillStyle = vg; c.fillRect(0, 0, W, H);
  for (const L of hud) DRAW[L.type](L, t);
  if (TL.attribution !== false && S.tiles) { c.save(); c.font = FONT('MM-Bold', 20); c.fillStyle = S.glow ? 'rgba(255,255,255,.55)' : 'rgba(0,0,0,.45)'; c.textAlign = 'right'; c.fillText('© 高德地图 AutoNavi', W - 20 * U, H - 24 * U); c.restore(); }
};
boot().catch(e => { window.__bootFailed = String(e && e.stack || e); console.error(window.__bootFailed); });
})();
