# 镜头表 spec 参考

目录：顶层字段 · 地点写法 · 11 种镜头（globe / locate / pins / route / flight / region / area / radiate / trip / overview / title）· 所有镜头通用字段 · 时间怎么算 · 常见组合

## 顶层

```json
{"size": "portrait", "fps": 30, "style": "amap", "tail": 0.6, "attribution": true, "shots": [ ... ]}
```

| 字段 | 取值 | 说明 |
|---|---|---|
| `size` | `portrait`（1080×1920）、`landscape`（1920×1080）、`square`（1080×1080），或 `[w, h]` | 竖屏发抖音/视频号/小红书，横屏发 B 站 |
| `style` | 瓦片：`amap` `amap-dark` `amap-gray` `amap-sepia` `satellite`；矢量：`dark` `light` `journal` `vintage` `neon` `ink` `blueprint` | 见 SKILL.md 样式表；街道级只能用瓦片样式 |
| `tail` | 秒 | 最后一镜结束后多停一会儿 |
| `attribution` | true/false | 高德瓦片样式右下角写「© 高德地图」；对外发布别关 |

## 地点写法

- 字符串：`"深圳"`、`"大理古城"`、`"深圳湾公园"`。编译时调高德解析并打印「地点 X → 解析结果（级别）[经纬度]」，**每次都要核对这几行**——同名地点会解析错。
- 解析不准时写坐标：`[113.97, 22.52]`（GCJ-02，高德坐标拾取器 lbs.amap.com/tools/picker 可取）。
- 换显示名：`{"name": "公司", "at": "腾讯滨海大厦"}` 或 `{"name": "老家", "at": [114.1, 22.6]}`。
- GPS、照片 EXIF、GPX 的坐标是 WGS-84：写 `{"name": "营地", "at": [99.72, 27.83], "wgs84": true}`，编译时转成高德坐标（否则偏 300–600 米）。

## 镜头

### globe — 地球俯冲
从转动的地球俯冲到一个地点，落点弹出标签。片头最常用。
```json
{"type": "globe", "to": "天安门", "zoom": 15.5, "dur": 7, "label": "天安门", "sub": "北京 · 东城区", "spin": -110, "hold": 1.5}
```
`zoom` 落地级别（城市 10–12，街区 14–16）；`spin` 起始时地球比目标偏多少经度（负＝从西边转过来）；`hold` 落地后停留秒数。矢量样式落地最多 8 级。

### locate — Vlog「我在这里」
地球俯冲 → 瞄准镜四角框收缩锁定（LOCKED 闪光）→ 坐标卡：地名逐字打出、经纬度（度分秒）从 0 滚到位、海拔（SRTM）、日期。10 秒左右，适合当 vlog 片头。
```json
{"type": "locate", "to": "双廊古镇", "zoom": 15.6, "dur": 6.5, "name": "大理 · 双廊", "sub": "洱海东岸 · DAY 3",
 "kicker": "I'M HERE", "date": "2026.10.03  07:42", "color": "#ffd23d", "hold": 3.8, "altitude": true}
```
`date` 是写死的字（拍摄时间），不是自动取；`altitude: false` 不查海拔。卫星样式最像「卫星锁定」，`amap-dark` 偏科技感。

### pins — 落点
一串地点依次落针、带涟漪。≤3 个时显示带底的标签卡。
```json
{"type": "pins", "places": ["深圳湾公园", "深圳湾体育中心"], "labels": ["散步", "看球"], "stagger": 0.45, "zoom": 13, "pin": "dot"}
```
`pin`：缺省＝水滴形；`dot`＝发光圆点；`stamp`＝邮戳（手账/复古样式缺省就是邮戳）。单个地点不写 `zoom` 时为 12 级。

### route — 路线描线
沿高德真实路线画线，交通工具沿线走。
```json
{"type": "route", "from": "深圳北站", "to": "广州塔", "mode": "driving", "via": ["东莞"], "vehicle": "car",
 "dur": 6, "follow": false, "odometer": true, "ghost": false, "second": false, "clear": false}
```
- `mode`：`driving` 驾车 / `walking` 步行 / `bicycling` 骑行（都走高德）/ `line` 直线 / `arc` 弧线
- `vehicle`：`car` `bus` `train` `plane` `walk` `bike` `dot` `none`（缺省按 mode 选）
- `follow: true`：镜头跟着车走（比整段框住近 `follow_zoom`＝2.2 级），结束拉回全段
- `odometer`：右上角公里数滚动；`{"from": 1200, "keep": true, "label": "累计"}` 可接着上一段累加
- `ghost`：先铺一条淡虚线预告全程；`second`：用第二路线色（返程、对比）
- `dur` 缺省按距离：50 km ≈ 3.8s，500 km ≈ 7s
- `elevation: true`：底部出海拔剖面卡（曲线随进度画出，实时海拔、已走里程、累计爬升），沿线取 120 个点查 SRTM 30m；登山、骑坡必开
- `pin_to: "flag"`：终点插旗（山顶、终点线）；`pin` 管起点样式
- `track`：用自己的轨迹代替高德路线：`"track": "跑步.gpx"`（GPX / GeoJSON，缺省按 WGS-84 转换）或坐标列表（缺省当高德坐标，WGS-84 加 `"wgs84": true`）；此时 `from`/`to` 可省，取轨迹首尾。短于 10 km 的里程表显示两位小数

### flight — 飞线
大圆航线，屏幕上向上拱起，飞机沿弧线飞。参数同 route（`mode` 固定为 arc，`vehicle` 缺省 plane）。

### region — 行政区高亮
高德行政区边界：先描边、再填色、再写名字。省、市、区县都行。
```json
{"type": "region", "names": ["深圳市", "东莞市", "惠州市"], "colors": ["#ff5a36", "#2f6bff", "#14b37d"], "stagger": 0.7, "opacity": 0.38, "labels": ["深", "莞", "惠"]}
```

### area — 地块轮廓（公园、景区、校园、小区）
高德不给面状地物边界：缺省按名字去 OpenStreetMap 查（自动换镜像、缓存、转高德坐标），选包含/最靠近高德落点的那块，同名地铁站会被排除。
```json
{"type": "area", "name": "桂林公园", "trace": true, "dur": 6, "label": "桂林公园", "color": "#ff5a36", "zoom": 17}
```
- `trace: true`：小人沿边界走一圈（同时描边），右上角显示周长；`vehicle` 可换
- 边界来源：缺省 OSM；`"osm_name"` 换 OSM 里的叫法；`"geojson": "x.geojson"`（缺省按 WGS-84 转换）；或 `"rings": [[[lng,lat],…]]`（加 `"wgs84": true` 转换）
- 编译打印「地块 X ← OSM way/…，N 个点」：点很少说明 OSM 画得粗，成片里轮廓是近似的；OSM 没有的地块会报错，换名字或给 geojson
- 街道级只能用 `amap` / `amap-dark` / `satellite`

### radiate — 一对多辐射
一个中心向多个地点放射飞线，每条落地亮点。总部→分部、产地→销地。
```json
{"type": "radiate", "from": "杭州", "to": ["北京", "上海", "广州"], "dur": 5, "stagger": 0.2, "fly_time": 1.3, "labels": true}
```

### trip — 多站旅程
一次写完整趟旅程：每段路线（高德）＋里程表累加＋左上角「A → B / DAY n · 日期 · km」＋到站落点/邮戳＋照片。
```json
{"type": "trip", "stops": ["深圳", "南宁", "昆明", "大理古城"], "mode": "driving", "stamp": true, "return": true,
 "stay": 2.6, "drive": null, "overview": true,
 "dates": {"南宁": "10.01", "昆明": "10.02"},
 "photos": {"大理古城": ["照片/a.jpg", {"image": "照片/b.jpg", "caption": "洱海边"}]}}
```
- `photos` 的键必须和 `stops` 里写的名字一字不差；每站最多 2 张，路径相对 spec 文件
- `drive`：每段固定秒数；缺省按里程（≈ 2.4 + 2.2×√(km/760)）
- `return: true`：最后用第二路线色把整条路原路开回去，里程表加倍
- `overview: false`：不先展示全程
- `elevation: true`：每段配海拔剖面卡（高原骑行、翻山自驾）

### overview — 回到全景
镜头框住到目前为止出现过的所有地点。片尾收束。`{"type": "overview", "dur": 2.5}`

### title — 标题卡
镜头不动，画面中央出标题。`{"type": "title", "text": "国庆自驾", "sub": "深圳 → 香格里拉", "dur": 2.2, "pos": "center"}`

## 通用字段（除 title 外的镜头都可写）

| 字段 | 说明 |
|---|---|
| `title` | 这一镜期间的大标题：字符串或 `{"text", "sub", "pos": "top|center|bottom", "size"}` |
| `caption` | 左上角说明卡：字符串或 `{"text", "sub"}` |
| `fly` | 从上一镜飞过来的秒数；缺省按距离和缩放差自动算（1–3.2s，远距离会先拉远再推近） |
| `clear` | true：这一镜开始时把之前的路线/落点/区域淡出（任何镜头都可写；从大区域推到街道级前一定要清，否则区域填色会染满全屏） |
| `dur` | 这一镜动画本身的时长（不含 fly） |

新镜头开始时，旧落点的文字自动淡出，只留点，避免拉远后标签挤成一团。

## 时间怎么算
一镜 = 飞行（fly）＋ 动画（dur）。编译时逐镜打印「到 X 秒」，总时长 = 最后一镜结束 + tail。想卡音乐节拍：先定每镜 dur，再把 `fly` 写死（不用自动值）。

## 常见组合

| 想做的视频 | 镜头序列 | 样式 |
|---|---|---|
| Vlog 片头「我在哪」 | locate（或 globe）| satellite / amap-dark |
| 登山徒步 | globe → route（walking，follow，elevation，pin_to flag）→ overview | satellite |
| 长途骑行 | globe → trip（bicycling，elevation，stay 短）→ overview | satellite / amap |
| 自驾/骑行复盘 | title → trip（return）→ overview | journal / vintage / amap |
| 两城出差/飞行 | pins → flight → pins | satellite / dark |
| 门店/仓库分布 | radiate 或 pins（多点）| dark / light |
| 区域介绍（城市群、行政区）| region → region（clear）| light / amap |
| 城市通勤/跑步路线 | route（walking/bicycling 或 track 导入 GPX，follow）| amap / amap-dark |
| 介绍一个公园/景点 | globe → area，或 region（所在区）→ pins（clear）→ route walking → area trace | satellite / amap |
