三个示例的 spec（不含照片）。用法：把你的照片放到 spec 同目录、命名为 `photo.jpg`，然后

```sh
~/.claude/skills/map-motion/scripts/make.sh fuji_shinkansen.json 成片.mp4
```

| 文件 | 场景 | 样式 | 说明 |
|---|---|---|---|
| `fuji_shinkansen.json` | 富士山 × 新干线（日本） | `satellite-world` | 境外用 Esri 卫星；机位是按画面估计的 |
| `yubeng_waterfall_live.json` | 雨崩神瀑 → 卡瓦格博 | `satellite` | 主峰用公开 WGS-84 坐标；Live 静态模拟 |
| `high_junk_peak_live.json` | 香港钓鱼翁 → 布袋澳 | `satellite` | 两点都来自高德 POI；Live 静态模拟 |
