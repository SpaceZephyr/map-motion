// 公共 HUD 件：缓动、淡入淡出、字体、描影文字、斜体数字、压暗渐变、照片牌、度分秒……
// 各个运行时（t3d.js 以及之后的新片型）共用：const K = HUD(canvas, TL); 再解构要用的。字体文件在 assets/fonts/（render.py 以 /asset/ 提供）。
window.HUD = (cv, TL) => {
'use strict';
const W = TL.width, H = TL.height, U = Math.min(W, H) / 1080, c = cv.getContext('2d'), Y = TL.color || '#f2ee3a';
cv.width = W; cv.height = H;
const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v)), lerp = (a, b, e) => a + (b - a) * e;
const E = {
  smooth: p => { p = clamp(p); return p * p * p * (p * (6 * p - 15) + 10); },
  out: p => 1 - Math.pow(1 - clamp(p), 3),
  back: p => { p = clamp(p); const s = 1.7, q = p - 1; return 1 + (s + 1) * q * q * q + s * q * q; },
};
const fade = (t, a, b, fi = 0.5, fo = 0.5) => clamp((t - a) / fi) * (b == null ? 1 : clamp((b - t) / fo));   // a 起淡入 fi 秒，b 前淡出 fo 秒
const FONT = (f, s) => `${s * U}px "${f}", "PingFang SC", sans-serif`;
const fmt = v => Math.round(v).toLocaleString('en-US');

async function loadFonts() {                                             // MM-Bold / MM-Black（思源黑）、MM-Hand（霞鹜文楷）、MM-Num（Anton 数字）
  for (const [fam, f] of [['MM-Bold', 'NotoSansSC-700'], ['MM-Black', 'NotoSansSC-900'], ['MM-Hand', 'LXGWWenKai-500'], ['MM-Num', 'Anton-400']]) {
    const ff = new FontFace(fam, `url(/asset/fonts/${f}.woff)`); await ff.load(); document.fonts.add(ff);
  }
}
async function loadImages(srcs) {                                        // → {src: Image}
  const IMG = {};
  await Promise.all(srcs.map(s => new Promise((res, rej) => { const im = new Image(); im.onload = () => { IMG[s] = im; res(); }; im.onerror = () => rej(new Error('图片加载失败 ' + s)); im.src = s; })));
  return IMG;
}

function shadowText(txt, x, y, font, color = '#fff', align = 'left', blur = 14) {
  c.save(); c.font = font; c.textAlign = align; c.textBaseline = 'alphabetic'; c.shadowColor = 'rgba(0,0,0,.75)'; c.shadowBlur = blur * U; c.shadowOffsetY = 2 * U;
  c.fillStyle = color; c.fillText(txt, x, y); c.shadowBlur = 0; c.shadowOffsetY = 0; c.fillText(txt, x, y); c.restore();
}
function numText(txt, x, y, size, color = Y, align = 'left') {           // Anton 加斜切，运动 App 那种斜体大数字
  c.save(); c.translate(x, y); c.transform(1, 0, -0.16, 1, 0, 0); shadowText(txt, 0, 0, `${size * U}px "MM-Num"`, color, align, 16); c.restore();
}
function outlineText(txt, x, y, font, color = '#fff', align = 'left', base = 'middle') {   // 黑描边白字（地图上的小标）
  c.save(); c.font = font; c.textAlign = align; c.textBaseline = base; c.lineJoin = 'round'; c.strokeStyle = 'rgba(0,0,0,.72)'; c.lineWidth = 7 * U;
  c.strokeText(txt, x, y); c.fillStyle = color; c.fillText(txt, x, y); c.restore();
}
function shade(y0, y1, a) {                                              // 从 y0 往 y1 的压暗渐变（亮背景上的白字靠它）
  if (a <= 0) return; const g = c.createLinearGradient(0, y0, 0, y1); g.addColorStop(0, `rgba(0,0,0,${a})`); g.addColorStop(0.55, `rgba(0,0,0,${a * 0.45})`); g.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = g; c.fillRect(0, Math.min(y0, y1), W, Math.abs(y1 - y0));
}
function panel(x, y, w, h, a = 0.55, r = 26) {                           // 半透明深色圆角底板
  c.save(); c.fillStyle = `rgba(8,10,14,${a})`; c.beginPath(); c.roundRect(x, y, w, h, r * U); c.fill(); c.restore();
}
function card(im, x, y, size, a, label) {                                // 白边照片牌 + 下方尖角，尖角对准 (x, y)
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
function pin(x, y, a, t, color = Y) {                                    // 脉冲落点
  c.save();
  for (const k of [0, 0.5]) { const q = (t * 0.8 + k) % 1; c.strokeStyle = color; c.globalAlpha = a * (1 - q); c.lineWidth = 5 * U; c.beginPath(); c.arc(x, y, (14 + 70 * q) * U, 0, 7); c.stroke(); }
  c.globalAlpha = a; c.fillStyle = '#fff'; c.beginPath(); c.arc(x, y, 14 * U, 0, 7); c.fill(); c.fillStyle = color; c.beginPath(); c.arc(x, y, 9 * U, 0, 7); c.fill();
  c.restore();
}
function dms(v, pos, neg) {                                              // 28.4367 → 28°26′12.1″N
  const x = Math.abs(v), d = Math.floor(x), m = Math.floor((x - d) * 60), s2 = Math.round(((x - d) * 60 - m) * 600) / 10;
  return `${d}°${String(m).padStart(2, '0')}′${s2.toFixed(1).padStart(4, '0')}″${v >= 0 ? pos : neg}`;
}
function title(txt, sub, y, a, size = 92) {                              // 居中大标题 + 副标题，从下往上浮入；长标题自动缩字号
  if (a <= 0 || !txt) return;
  c.save(); c.globalAlpha = a; const k = E.out(a);
  c.font = FONT('MM-Black', size); const ts = size * Math.min(1, (W - 100 * U) / c.measureText(txt).width);
  shadowText(txt, W / 2, y + (1 - k) * 30 * U, FONT('MM-Black', ts), '#fff', 'center', 22);
  if (sub) shadowText(sub, W / 2, y + 70 * U + (1 - k) * 30 * U, FONT('MM-Bold', 38), 'rgba(255,255,255,.92)', 'center');
  c.restore();
}
function attribution(txt) {
  if (!txt) return; c.save(); c.font = FONT('MM-Bold', 17); c.fillStyle = 'rgba(255,255,255,.55)'; c.textAlign = 'right'; c.fillText(txt, W - 18 * U, H - 14 * U); c.restore();
}
return { W, H, U, c, Y, clamp, lerp, E, fade, FONT, fmt, loadFonts, loadImages, shadowText, numText, outlineText, shade, panel, card, pin, dms, title, attribution };
};
