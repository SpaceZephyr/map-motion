---
name: map-3d
description: "3D 地形地图视频：真实立体山体（卫星贴图 + 高程）上做轨迹/路线/地点动画，竖屏 MP4。卫星地球俯冲 → 整条路线 3D 鸟瞰 → 镜头贴着人/车沿路线走（走过的线变黄、里程、海拔、累计爬升、小地图、底部海拔剖面、沿途弹照片）→ 拉回全景出总数据；或单个地点俯冲后绕着转一圈（地名、经纬度、海拔）。支持徒步/登山（GPX 或 OSM 小路连线）、自驾、骑行、步行（高德路线规划）、景点/雪山环绕。用 map-motion 的引擎（MapLibre 渲染）。当用户说「3D 地图」「立体地图」「3D 地形」「像 Google Earth 那样」「两步路/六只脚那种 3D 轨迹回放」「3D 徒步轨迹」「自驾路线 3D」「山体立体」「环绕雪山」「3D 版本」，或拿来 GPX/路线要做有山体起伏的地图视频时使用。平面风格（手账、霓虹、高德标准等）、多镜头组合、飞线、行政区仍用 map-motion 主 skill。"
---

# 3D 地形 map-3d

一份 spec（`"mode": "3d"`）→ 一段竖屏 3D 片子。渲染引擎是 map-motion（`scripts/terrain3d.py` 算镜头，`scripts/runtime/t3d.js` + MapLibre GL 出画面），本 skill 管流程：选路线来源 → 写 spec → 连续小段检查 → 出片。

| 片型 | 节奏（缺省） | 用在 |
|---|---|---|
| **路线**（有 `track`） | 0–6s 地球俯冲 → 6–8.6s 整条路线鸟瞰、白线画出、标题 → 2.4s 压低贴到起点 → 跟随 10–26s（按长度）→ 6s 拉回全景、绕一点、总里程/爬升/最高海拔 | 徒步、登山、自驾、骑行、跑步、步道 |
| **单点**（只有 `place`） | 0–6s 俯冲 → 8s 绕着转（缺省 90°），底部地名卡＋经纬度＋海拔滚动 | 雪山、景点、营地、「我在这里」 |

## 准备
- map-motion 引擎（同一仓库根目录 `scripts/`）、uv、ffmpeg、Chromium（`uv run --with playwright playwright install chromium`）。高德 key 只在用地名或高德路线时需要（见 map-motion 主 skill）。
- `X=~/.claude/skills/map-3d/scripts/m3d.sh`
  - `$X check spec.json` 在每个关键时刻前渲 0.6 秒连续小段，取末帧拼成一张图（5–6 分钟）
  - `$X make spec.json 成片.mp4` 整片 + 预览 GIF（约 1 秒一帧：30 秒片子 15–25 分钟，**放后台跑**）

## 流程

### 1. 定路线来源（按可信度）
| 用户给了什么 | `track` 写法 | 说明 |
|---|---|---|
| GPX / KML 转的 GeoJSON（两步路、六只脚、Strava、Keep、手表） | `"track": "xx.gpx"` | 最准，就是真实走过的线。WGS-84，不用转 |
| 只说了起终点，开车/骑车/城里走 | `{"mode": "driving" \| "bicycling" \| "walking", "from": "地名", "to": "地名", "via": [...]}` | 高德路线规划（GCJ → 自动转 WGS）。景区台阶路高德步行也常有（泰山红门→南天门实测可用） |
| 山野徒步，没有 GPX | `{"via": [途经点…], "margin": 0.02}` | 沿 OpenStreetMap 小路取最短路连起来。山里 OSM 常断头：报「不连通」就加中间点、缩短，或请用户给 GPX |
| 一串坐标 | `[[lng, lat], …]` | 直接用 |
| 只有一个地方 | 不写 `track`，写 `"place"` | 单点环绕 |

地名一律经高德解析，编译会打印「地点 X → 解析结果」——**每行核对**（同名 POI 会解析错）。山峰 POI 可能偏几公里，主峰直接写公开资料的 WGS 坐标。

### 2. 写 spec
从 `examples/` 挑最像的复制改：

| 例子 | 内容 |
|---|---|
| `hike_osm_yubeng.json` | 雨崩：南争垭口 → 上村 → 下村 → 神瀑，OSM 小路连线，9.8 km |
| `walk_amap_taishan.json` | 泰山红门 → 中天门 → 南天门，高德步行，6.1 km 爬升 1181 m |
| `drive_amap_shangrila.json` | 香格里拉 → 飞来寺，高德驾车 171 km（长路线自动拉远镜头） |
| `place_orbit_meili.json` | 卡瓦格博单点俯冲 + 环绕 |

| 字段 | 说明 |
|---|---|
| `title` / `sub` | 鸟瞰和片尾标题；长标题自动缩字号 |
| `marks` | 地名小标：`{"name", "at"}`，`at` 可写地名；名字里可以带海拔（「卡瓦格博 6740m」） |
| `photos` | 沿途照片：`{"image", "at" 或 "km", "label"}`；走到那里停 `pause`（2.2s）弹大图，之后缩成小牌子留在原地。有人像的照片提醒用户这是要公开的 |
| `gcj` | `true` = spec 里的数字坐标是高德坐标；缺省按 WGS-84 |
| `zoom` / `pitch` | 跟随镜头，缺省按长度自动（10 km 内 15.1 级；170 km 约 11.7 级）/ 62° |
| `exaggeration` | 地形夸张，缺省 1.35；平原路线可加到 2 |
| `follow` `pause` `dive` `overview` `swoop` `end` | 各段秒数 |
| `color` | 走过的线和数字颜色，缺省 `#f2ee3a` |
| 单点：`place` `name` `ele` `zoom` `pitch` `bearing` `turn` `orbit` | `ele` 写已知海拔（高程数据 30 m 网格会削峰：卡瓦格博 DEM 只有 6469 m） |

### 3. 检查（必做，用连续小段，不要只看单帧）
```sh
cd 项目目录 && $X check spec.json      # → spec-check.png，Read 它
```
逐项看：
- 俯冲末/鸟瞰：整条线在画面里、标题不压线；**没有黑块、没有直边断口**（远处地形缺瓦片的样子）
- 跟随：人在画面中部、前方能看到白线；顶部里程和小地图、底部海拔剖面清楚
- 片尾：整条黄线都在画面内，总数据卡不压线
- 不对就改 `zoom`/`pitch`/`exaggeration` 或 marks，再 check

### 4. 出片（后台）
```sh
$X make spec.json 名字.mp4             # 同时出 名字.gif（270px 预览）
```
首次跑会下载几千张卫星/高程瓦片（缓存在 `~/.cache/map-motion/tiles/`，重渲很快）。

### 5. 交付
说清：文件位置、时长；路线来自哪（GPX / 高德规划 / OSM 小路推测——推测的要明说「不是你实际走的线」）；里程、爬升是按 AWS 高程数据算的（和手表数字会差 5–15%）；影像 Esri、地形 Mapzen/AWS 已在画面右下角署名。

## 踩过的坑
- 单帧 `--stills` 一切正常，连续出片却露黑块/直边断口——MapLibre 连续换相机时远处瓦片会漏。所以检查一律用 `check`（连续小段）。引擎已处理：12.2 级后换平面投影、天空 2D 自画、全景俯角 40–44°。
- MapLibre 5.6 在地球↔地形切换时抛 `clearFadeHold`，已锁 5.24。
- 国内也用 Esri 卫星（WGS-84）：高德卫星是 GCJ，和地形、GPX 对不上。所以 3D 片里所有高德来的点都转回 WGS。
- 雪山上白字看不清 → HUD 上下有压暗渐变；顶部 290px 内的地名小标会自动淡出，避免压住里程。
- 软件 WebGL（SwiftShader）慢且吃 CPU，别同时跑两个整片。
