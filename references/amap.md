# 高德接入说明

## key
- 用「Web服务」类型的 key（高德开放平台 → 控制台 → 应用管理 → 添加 Key → 服务平台选 Web服务）。JS API 的 key 不能用于这里。
- 放法（任选）：`export AMAP_KEY=…`，或写进 `~/.config/map-motion/amap_key`（`chmod 600`）。不要把 key 写进 spec 或项目目录（项目可能被同步/分享）。
- 免费额度：约 3 次/秒、每日数千次。`amap.py` 每次请求间隔 0.35s、被限流（10021）自动退避；所有响应缓存在 `~/.cache/map-motion/api/`，同一片子重编译不再消耗配额。

## 用到的接口（amap.py）
| 函数 | 接口 | 备注 |
|---|---|---|
| `geocode(name)` | `/v3/geocode/geo`，必要时 `/v3/place/text` | 行政区名先信地理编码；编码只到兴趣点/道路/公交站级时再用 POI 搜索取第一个结果 |
| `route(o, d, mode)` | 驾车 `/v3/direction/driving`（`via` → waypoints，最多 16 个）、步行 `/v3/direction/walking`、骑行 `/v4/direction/bicycling` | 折线按跨度自适应抽稀（几千点 → 几百点）；步行限 100 km 内 |
| `district(name)` | `/v3/config/district?extensions=all` | 返回边界多环（含海岛）；同名区县可能重名，写全称如「朝阳区」可能返回北京的，必要时写「长春市朝阳区」 |

命令行自查：`uv run --with certifi python amap.py geo 地名` / `route A B --mode walking` / `district 广东省`。

## 瓦片底图（render.py 代理并缓存到 ~/.cache/map-motion/tiles/）
| 源 | 说明 |
|---|---|
| amap | 标准路网 `wprd0x.is.autonavi.com … style=7 scl=2`，512px 高清 |
| sat | 卫星 `webst0x.is.autonavi.com … style=6`，256px（按高一级取，等效高清） |
| lbl | 卫星上叠加的路名地名层 `style=8 ltype=4` |

`amap-dark` 是把标准路网瓦片用滤镜反色得到的，不是高德官方暗色。

**使用边界**：直接取瓦片属于非官方用法，个人视频、学习交流一般没问题；**商业投放（广告片、付费项目）需要高德地图的商业授权**，或改用矢量样式（dark/light/journal/vintage 不取高德瓦片；省界来自阿里 DataV、世界陆地来自 Natural Earth，商用同样先确认其条款）。成片保留右下角「© 高德地图」署名。

## 坐标系
高德全线 GCJ-02（路线、边界、瓦片三者一致，叠在一起不会偏）。内置的世界陆地轮廓是 WGS-84，只在地球/全国尺度出现，几百米的差看不出来。GPS 设备、手机照片 EXIF、GPX 是 WGS-84：直接画在高德底图上会偏 300–600 米。spec 里写 `{"at": [lng, lat], "wgs84": true}`，编译时用 `amap.wgs2gcj` 转换。

## 地图审图
内置中国省界来自阿里 DataV（高德数据），含南海九段线；不要自己删改国界、不要只画大陆不画台湾和南海诸岛。公开发布的地图内容在国内受《地图管理条例》约束，涉及国界的成片对外商用前建议走审图号或用官方标准地图底图。
