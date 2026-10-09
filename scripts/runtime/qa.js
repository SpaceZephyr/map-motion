// 自动质检：记下主画布上每段文字、每张图片的屏幕框，外加黑块比例，交给 render.py 在本地判「出画 / 重叠 / 黑块」。
// 两个运行时（mm.js、t3d.js）共用；只拦主画布（id="c"），离屏画布（相纸、Live 帧缓存）不算。
// 运行时想跳过黑块检查（例如 3D 片的太空阶段本来就是黑的）就设 window.__qaSkipBlack = true。
(() => {
'use strict';
let rec = null;
const isMain = ctx => ctx.canvas && ctx.canvas.id === 'c';
function box(ctx, text, x, y) {
  if (!rec || !isMain(ctx) || ctx.globalAlpha < 0.25 || !String(text).trim()) return;
  const m = ctx.measureText(text), l = m.actualBoundingBoxLeft, r = m.actualBoundingBoxRight, a = m.actualBoundingBoxAscent, d = m.actualBoundingBoxDescent;
  const T = ctx.getTransform(), pts = [[x - l, y - a], [x + r, y - a], [x - l, y + d], [x + r, y + d]].map(([px, py]) => [T.a * px + T.c * py + T.e, T.b * px + T.d * py + T.f]);
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  rec.push({ k: 'text', s: String(text), x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) });
}
for (const fn of ['fillText', 'strokeText']) {
  const orig = CanvasRenderingContext2D.prototype[fn];
  CanvasRenderingContext2D.prototype[fn] = function (text, x, y, ...rest) { box(this, text, x, y); return orig.call(this, text, x, y, ...rest); };
}
const origImg = CanvasRenderingContext2D.prototype.drawImage;
CanvasRenderingContext2D.prototype.drawImage = function (...a) {
  const src = a[0], photo = (src instanceof HTMLImageElement && src.src.includes('/file/')) || (src && src.pr);   // 只记用户照片和相纸卡片；瓦片、地球纹理不算
  if (rec && photo && isMain(this) && a.length >= 5 && this.globalAlpha >= 0.25) {
    const [x, y, w, h] = a.length >= 9 ? a.slice(5, 9) : a.slice(1, 5);
    if (Math.abs(w * h * this.getTransform().a * this.getTransform().d) < this.canvas.width * this.canvas.height * 0.5) {   // 铺满半屏以上的是虚化背景，不算
      const T = this.getTransform();
      rec.push({ k: 'image', s: '', x0: T.a * x + T.c * y + T.e, y0: T.b * x + T.d * y + T.f, x1: T.a * (x + w) + T.c * (y + h) + T.e, y1: T.b * (x + w) + T.d * (y + h) + T.f });
    }
  }
  return origImg.apply(this, a);
};
let small;
window.__qaBegin = () => { rec = []; window.__qaSkipBlack = false; };
window.__qaEnd = () => {
  const out = { boxes: rec || [], black: null }; rec = null;
  if (!window.__qaSkipBlack) {                                            // 缩到 108×192 统计近纯黑像素
    const cv = window.__canvas; small = small || Object.assign(document.createElement('canvas'), { width: 108, height: 192 });
    const g = small.getContext('2d', { willReadFrequently: true }); origImg.call(g, cv, 0, 0, 108, 192);
    const d = g.getImageData(0, 0, 108, 192).data; let n = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i] < 3 && d[i + 1] < 3 && d[i + 2] < 3) n++;   // 没画出来的区域是纯色 0；阴影缩小后平均不到这么黑
    out.black = n / (108 * 192);
  }
  out.boxes = out.boxes.map(b => ({ ...b, x0: Math.round(b.x0), y0: Math.round(b.y0), x1: Math.round(b.x1), y1: Math.round(b.y1) }));
  return out;
};
})();
