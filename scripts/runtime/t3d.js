// map-motion 3D 地形运行时：MapLibre GL（地球投影 + raster-dem 地形 + Esri 卫星）画地图和轨迹线，2D 画布叠 HUD。
// 坐标 WGS-84。逐帧相机由 terrain3d.py 算好（TL.frames[i] = [lng, lat, zoom, pitch, bearing, 已走 km]）。
// 对外接口和 mm.js 一样：window.prepare(t)（异步，等瓦片）→ window.renderFrame(t) → window.__canvas。
(() => {
'use strict';
const TL = window.MM_TIMELINE, PH = TL.phase;
const cv = document.getElementById('c'); window.__canvas = cv;
const K = HUD(cv, TL), { W, H, U, c, clamp, lerp, E, fade, FONT, fmt, shadowText, numText, outlineText, shade, panel, card, pin, dms } = K;   // 公共 HUD 件见 hud.js
const md = document.getElementById('m'); md.style.width = W + 'px'; md.style.height = H + 'px';
const Y = TL.color, TR = TL.track, ST = TL.stats, STEP = TR[1][3] - TR[0][3];

// 轨迹上第 d km 的点：[lng, lat, 海拔, km, 累计爬升]
function at(d) {
  const x = clamp(d / STEP, 0, TR.length - 1), i = Math.min(TR.length - 2, Math.floor(x)), f = x - i, a = TR[i], b = TR[i + 1];
  return a.map((v, k) => lerp(v, b[k], f));
}
const lineTo = d => { const i = Math.min(TR.length - 1, Math.floor(d / STEP)); const pts = TR.slice(0, i + 1).map(p => [p[0], p[1]]); const e = at(d); pts.push([e[0], e[1]]); return pts; };
const gj = coords => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords.length > 1 ? coords : [coords[0], coords[0]] } });

let map, IMG = {};
async function boot() {
  await K.loadFonts(); IMG = await K.loadImages(TL.layers.map(L => L.image));
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
  if (TL.sun) SUN.boot();
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
  if (TL.sun) pend.push(SUN.prepare(t));
  await Promise.all(pend); await settle();
  for (let k = 0; k < 6 && !map.areTilesLoaded(); k++) await settle();   // 连续出帧时远处地形瓦片会漏：没齐就再等
};

// ================= HUD
const proj = (ll, ele) => { const p = map.project(ll); return [p.x, p.y]; };
const onScreen = p => p[0] > -50 && p[0] < W + 50 && p[1] > -50 && p[1] < H + 50;
function drawMarks(t, a) {
  if (a <= 0) return;
  for (const m of TL.marks) {
    const p = proj(m.at); if (!onScreen(p)) continue;
    c.save(); c.globalAlpha = a * clamp((p[1] - (TL.sun ? 470 : 290) * U) / (60 * U));        // 别压住顶部的标题和里程
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

const drawTitle = (t, a, y) => K.title(TL.title, TL.sub, y, a);

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
  const p = proj(P.at); pin(p[0], p[1], a, t); c.save();
  const k = E.out(clamp((t - PH.dive) / 0.9)), y = H - 330 * U + (1 - k) * 60 * U; c.globalAlpha = a * k; const dm = dms;
  shadowText(P.name, 64 * U, y, FONT('MM-Black', 84), '#fff', 'left', 20);
  shadowText(`${dm(P.at[1], 'N', 'S')}   ${dm(P.at[0], 'E', 'W')}`, 66 * U, y + 70 * U, `${36 * U}px "MM-Num"`, 'rgba(255,255,255,.9)');
  shadowText('海拔', 66 * U, y + 150 * U, FONT('MM-Bold', 30), '#fff'); numText(`${fmt(P.ele * clamp((t - PH.dive) / 1.6))} m`, 140 * U, y + 156 * U, 72);
  c.restore();
}

// ================= 光线推演（sunlight.py 出的 TL.sun）：太阳方位/高度驱动山体明暗和天空；时钟、罗盘、关键时刻表
// series[i] = [方位, 高度, 当地分钟, 山峰受光余量°, 机位受光余量°]（余量 > 0 即照到）
const SUN = TL.sun && (() => {
  const S = TL.sun, N = S.series.length; let cur = S.series[0], lastAz = null, KD = 0;   // KD：0＝俯冲时的白天样子，1＝推演里的真实光线
  const dest = (ll, brg, km) => {
    const d = km / 6371, b = brg * Math.PI / 180, la1 = ll[1] * Math.PI / 180, lo1 = ll[0] * Math.PI / 180;
    const la2 = Math.asin(Math.sin(la1) * Math.cos(d) + Math.cos(la1) * Math.sin(d) * Math.cos(b));
    return [(lo1 + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(la1), Math.cos(d) - Math.sin(la1) * Math.sin(la2))) * 180 / Math.PI, la2 * 180 / Math.PI];
  };
  const mix = (a, b, e) => a.map((v, k) => Math.round(lerp(v, b[k], e)));
  const SKY = [[-10, [6, 10, 26], [18, 26, 56]], [-4, [20, 32, 74], [92, 88, 138]], [-1, [38, 56, 116], [232, 138, 92]], [3, [60, 102, 174], [255, 194, 138]], [10, [74, 124, 196], [214, 228, 240]]];
  const gold = () => KD * clamp(cur[3] / 1.2) * clamp((6 - cur[1]) / 3);       // 山顶照到了、太阳还低：金色
  const day = () => lerp(1, clamp((cur[1] + 4) / 10), KD);
  const hhmm = m => `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(Math.floor(m % 60)).padStart(2, '0')}`;
  const rayLen = S.spot ? Math.max(4, Math.hypot((S.spot[0] - S.peak[0]) * 98, (S.spot[1] - S.peak[1]) * 111) * 0.55) : 6;

  function boot() {
    map.addSource('hs', { type: 'raster-dem', tiles: ['/tile/dem/{z}/{x}/{y}'], encoding: 'terrarium', tileSize: 256, maxzoom: 14 });
    map.addLayer({ id: 'hill', type: 'hillshade', source: 'hs', paint: { 'hillshade-illumination-anchor': 'map', 'hillshade-exaggeration': 0.75, 'hillshade-accent-color': 'rgba(0,0,0,0)' } }, 'full-case');
    map.addSource('sight', { type: 'geojson', data: gj(S.spot ? [S.spot, S.peak] : [S.peak]) });
    map.addSource('ray', { type: 'geojson', data: gj([S.peak]) });
    map.addLayer({ id: 'sight', type: 'line', source: 'sight', paint: { 'line-color': '#fff', 'line-width': 3 * U, 'line-opacity': S.spot ? 0.85 : 0, 'line-dasharray': [2, 2] } });
    map.addLayer({ id: 'ray-glow', type: 'line', source: 'ray', layout: { 'line-cap': 'round' }, paint: { 'line-color': Y, 'line-width': 20 * U, 'line-blur': 12 * U, 'line-opacity': 0 } });
    map.addLayer({ id: 'ray', type: 'line', source: 'ray', layout: { 'line-cap': 'round' }, paint: { 'line-color': Y, 'line-width': 5 * U, 'line-opacity': 0 } });
  }
  function prepare(t) {
    cur = S.series[clamp(Math.round(t * TL.fps), 0, N - 1)]; KD = E.smooth((t - PH.dive + 1.0) / 1.8);   // 俯冲落地前后天色才暗下去
    const [az, al] = cur, g = gold(), d = day(), ra = clamp((al + 1) / 2) * 0.9;
    map.setPaintProperty('hill', 'hillshade-illumination-direction', az);
    map.setPaintProperty('hill', 'hillshade-highlight-color', `rgba(255,${Math.round(lerp(236, 168, g))},${Math.round(lerp(214, 84, g))},${((0.12 + 0.5 * g) * clamp((al + 3) / 3)).toFixed(3)})`);
    map.setPaintProperty('hill', 'hillshade-shadow-color', `rgba(8,16,44,${lerp(0.78, 0.42, d).toFixed(3)})`);
    map.setPaintProperty('sat', 'raster-brightness-max', lerp(0.42, 1, d));
    map.setPaintProperty('sat', 'raster-saturation', lerp(-0.45, 0.05, d));
    map.setPaintProperty('ray', 'line-opacity', ra * KD); map.setPaintProperty('ray-glow', 'line-opacity', ra * 0.5);
    if (lastAz !== null && Math.abs(az - lastAz) < 0.05) return Promise.resolve();
    lastAz = az; return setData('ray', gj([S.peak, dest(S.peak, az, rayLen)]));   // 光从这个方向照到山顶
  }
  function sky() {
    const al = cur[1]; let k = 0; while (k < SKY.length - 2 && al > SKY[k + 1][0]) k++;
    const [a0, t0, b0] = SKY[k], [a1, t1, b1] = SKY[k + 1], e = clamp((al - a0) / (a1 - a0));
    return [mix(SKY[4][1], mix(t0, t1, e), KD), mix(SKY[4][2], mix(b0, b1, e), KD)];
  }
  function behind() {                                                     // 太阳本体：画在地图下面，地形自然挡住
    const [az, al] = cur; if (al < -1.5 || F[2] < 8) return;
    const fov = map.transform.fov * Math.PI / 180, f = (H / 2) / Math.tan(fov / 2), daz = ((az - F[4] + 540) % 360) - 180;
    if (Math.abs(daz) > 75) return;
    const x = W / 2 + f * Math.tan(daz * Math.PI / 180), y = H / 2 - f * Math.tan((al - (F[3] - 90)) * Math.PI / 180);
    c.save(); c.globalCompositeOperation = 'screen';
    const g = c.createRadialGradient(x, y, 0, x, y, 260 * U); g.addColorStop(0, 'rgba(255,214,140,.95)'); g.addColorStop(0.12, 'rgba(255,190,100,.55)'); g.addColorStop(1, 'rgba(255,140,60,0)');
    c.fillStyle = g; c.fillRect(x - 260 * U, y - 260 * U, 520 * U, 520 * U);
    c.fillStyle = '#fff6e0'; c.beginPath(); c.arc(x, y, 22 * U, 0, 7); c.fill(); c.restore();
  }
  function compass(x, y, r, a) {                                          // 北朝上：白扇形＝镜头朝向，金点＝太阳方位
    if (a <= 0) return; const [az, al] = cur, P = deg => [Math.sin(deg * Math.PI / 180), -Math.cos(deg * Math.PI / 180)];
    c.save(); c.globalAlpha = a; c.translate(x, y);
    c.fillStyle = 'rgba(8,10,14,.5)'; c.beginPath(); c.arc(0, 0, r, 0, 7); c.fill(); c.strokeStyle = 'rgba(255,255,255,.75)'; c.lineWidth = 2 * U; c.stroke();
    const hf = Math.atan(Math.tan(map.transform.fov * Math.PI / 360) * W / H) * 180 / Math.PI, b = F[4];
    c.fillStyle = 'rgba(255,255,255,.2)'; c.beginPath(); c.moveTo(0, 0); c.arc(0, 0, r * 0.92, (b - hf - 90) * Math.PI / 180, (b + hf - 90) * Math.PI / 180); c.closePath(); c.fill();
    for (let k = 0; k < 360; k += 30) { const [sx, sy] = P(k); c.beginPath(); c.moveTo(sx * r * 0.9, sy * r * 0.9); c.lineTo(sx * r, sy * r); c.stroke(); }
    for (const [lab, k] of [['N', 0], ['E', 90], ['S', 180], ['W', 270]]) { const [sx, sy] = P(k); shadowText(lab, sx * r * 0.72, sy * r * 0.72 + 9 * U, `${26 * U}px "MM-Num"`, lab === 'N' ? Y : '#fff', 'center', 4); }
    const [sx, sy] = P(az), up = al > -0.3;
    c.strokeStyle = up ? Y : 'rgba(255,255,255,.5)'; c.lineWidth = 3 * U; c.beginPath(); c.moveTo(0, 0); c.lineTo(sx * r * 0.8, sy * r * 0.8); c.stroke();
    c.fillStyle = up ? Y : 'rgba(200,210,230,.8)'; c.beginPath(); c.arc(sx * r * 0.8, sy * r * 0.8, 13 * U, 0, 7); c.fill();
    c.restore();
    shadowText(`方位 ${az.toFixed(0)}°`, x, y + r + 44 * U, FONT('MM-Bold', 28), '#fff', 'center', 8);
  }
  function events(t, a) {                                                 // 关键时刻表：到点打勾、高亮一下
    if (a <= 0) return; const ev = S.events, rh = 92 * U, x0 = 48 * U, x1 = W - 48 * U, y0 = H - 96 * U - ev.length * rh - 36 * U;
    c.save(); c.globalAlpha = a; panel(x0, y0, x1 - x0, ev.length * rh + 36 * U, 0.55);
    ev.forEach((e, i) => {
      const y = y0 + 18 * U + i * rh, done = e.t != null ? t >= e.t : (e.time !== '—' && t >= PH.l1), hl = e.t != null ? fade(t, e.t, e.t + 1.6, 0.15, 0.8) : 0;
      if (hl > 0) { c.fillStyle = `rgba(255,194,74,${0.28 * hl})`; c.beginPath(); c.roundRect(x0 + 8 * U, y + 4 * U, x1 - x0 - 16 * U, rh - 8 * U, 18 * U); c.fill(); }
      const cx = x0 + 46 * U, cy = y + rh / 2;
      c.lineWidth = 3 * U; c.strokeStyle = done ? Y : 'rgba(255,255,255,.55)'; c.fillStyle = Y; c.beginPath(); c.arc(cx, cy, 17 * U, 0, 7); done ? c.fill() : c.stroke();
      if (done) { c.strokeStyle = '#1a1a1a'; c.lineWidth = 4 * U; c.beginPath(); c.moveTo(cx - 8 * U, cy); c.lineTo(cx - 2 * U, cy + 7 * U); c.lineTo(cx + 9 * U, cy - 7 * U); c.stroke(); }
      shadowText(e.name, x0 + 86 * U, y + 44 * U, FONT('MM-Bold', 34), done ? '#fff' : 'rgba(255,255,255,.7)', 'left', 6);
      if (e.note) shadowText(e.note, x0 + 86 * U, y + 78 * U, FONT('MM-Bold', 22), 'rgba(255,255,255,.6)', 'left', 4);
      numText(e.time, x1 - 30 * U, y + 66 * U, 54, done ? Y : 'rgba(255,255,255,.6)', 'right');
    });
    c.restore();
  }
  function render(t) {
    const g = gold(), nt = (1 - day()) * 0.45;
    if (nt > 0) { c.save(); c.globalCompositeOperation = 'multiply'; c.fillStyle = `rgba(70,90,150,${nt})`; c.fillRect(0, 0, W, H); c.restore(); }   // 天没亮：整体压蓝
    if (g > 0) {                                                          // 日照金山：山顶一圈暖光
      const p = proj(S.peak), r = 420 * U; c.save(); c.globalCompositeOperation = 'soft-light';
      const gr = c.createRadialGradient(p[0], p[1], 0, p[0], p[1], r); gr.addColorStop(0, `rgba(255,150,40,${0.9 * g})`); gr.addColorStop(1, 'rgba(255,150,40,0)');
      c.fillStyle = gr; c.fillRect(p[0] - r, p[1] - r, 2 * r, 2 * r); c.restore();
    }
    const a0 = fade(t, PH.dive - 0.6, null, 0.8), la = fade(t, PH.l0 - 0.05, PH.l1 + 0.3, 0.5, 0.5);   // 时钟罗盘等标题退完再出，片尾标题等它们退完再进
    shade(0, 560 * U, 0.62 * a0); shade(H, H - 700 * U, 0.7 * a0);
    drawMarks(t, fade(t, PH.dive - 0.4, null, 0.8));
    drawTitle(t, fade(t, PH.dive - 1.0, PH.l0 - 0.1, 0.8, 0.5), 240 * U);
    drawTitle(t, fade(t, PH.l1 + 0.9, null, 0.8), 240 * U);
    if (la > 0) {
      c.save(); c.globalAlpha = la;
      numText(hhmm(cur[2]), 56 * U, 196 * U, 132, '#fff');
      shadowText(`${S.date}  ${S.rise ? '日出' : '日落'}`, 60 * U, 258 * U, FONT('MM-Bold', 32), '#fff');
      shadowText(`太阳高度 ${cur[1] >= 0 ? '+' : ''}${cur[1].toFixed(1)}°`, 60 * U, 308 * U, FONT('MM-Bold', 32), cur[1] > -0.3 ? Y : 'rgba(255,255,255,.8)');
      if (g > 0.25) {
        const q = 0.6 + 0.4 * Math.sin(t * 6); c.globalAlpha = la * clamp((g - 0.25) / 0.2);
        c.fillStyle = Y; c.beginPath(); c.arc(74 * U, 362 * U, 12 * U * q + 4 * U, 0, 7); c.fill();
        shadowText('日照金山中', 98 * U, 376 * U, FONT('MM-Black', 40), Y);
      }
      c.restore();
      compass(W - 170 * U, 170 * U, 108 * U, la);
    }
    events(t, fade(t, PH.l0 - 0.2, null, 0.6));
    K.attribution(TL.attribution);
  }
  return { boot, prepare, sky, behind, render };
})();

window.renderFrame = t => {
  const sk = clamp((F[2] - 4) / 3);                                       // 天空自己画：MapLibre 的天空在地球/地形切换后常出不来，露出黑底
  const [top, bot] = TL.sun ? SUN.sky() : [[74, 124, 196], [214, 228, 240]];
  const g = c.createLinearGradient(0, 0, 0, H * 0.6);
  g.addColorStop(0, `rgb(${top.map(v => lerp(0, v, sk))})`); g.addColorStop(1, `rgb(${bot.map(v => lerp(0, v, sk))})`);
  c.fillStyle = g; c.fillRect(0, 0, W, H); if (TL.sun) SUN.behind(); c.drawImage(map.getCanvas(), 0, 0, W, H);
  if (F[2] < 6) window.__qaSkipBlack = true;                              // 太空本来就是黑的
  if (TL.sun) return SUN.render(t);
  const d = F[5], hudA = fade(t, PH.f0 - 0.4, PH.f1 + 0.9, 0.6, 0.6), topA = Math.max(hudA, fade(t, PH.dive - 1.0, PH.f0 - 0.4, 0.8, 0.6), fade(t, PH.f1 + 1.0, null, 0.8));
  shade(0, 520 * U, topA * 0.62); shade(H, H - 620 * U, Math.max(hudA, fade(t, PH.f1 + 1.4, null, 0.7), TL.place ? fade(t, PH.dive - 0.6, null, 0.8) : 0) * 0.7);   // 雪山上白字看不清：上下压暗
  drawMarks(t, fade(t, PH.dive - 0.4, null, 0.8));
  drawPhotos(t); drawPlace(t);
  drawHiker(t, d, fade(t, PH.f0 - 0.8, null, 0.6));
  drawTitle(t, fade(t, PH.dive - 1.0, PH.f0 - 0.4, 0.8, 0.6), 240 * U);
  drawTitle(t, fade(t, PH.f1 + 1.0, null, 0.8), 240 * U);
  drawFollowHud(t, d, hudA);
  drawStats(t, fade(t, PH.f1 + 1.4, null, 0.7));
  K.attribution(TL.attribution);
};

boot().then(() => { window.__ready = true; }, e => { window.__bootFailed = String(e && e.stack || e); });
})();
