---
name: travel-vlog
description: "旅行 vlog 地图视频：用户给一组旅行照片（和一张自己的照片），自动按照片 GPS 和拍摄时间找出机位、排好顺序、沿真实步行/驾车路线连起来；用照片生成用户的 Q 版卡通形象，卡通小人沿路线一颠一颠地走，右上角里程累加，走到每个机位停下「咔嚓」拍照、照片啵地弹出（写着第几站、已走多少公里），再走向下一站，最后照片墙 + 总里程收尾；配原创欢快 BGM 和脚步、快门、啵、叮音效，弹照片踩在拍点上。手账风竖屏 MP4。用 map-motion 引擎。当用户说「旅行 vlog」「把旅行照片做成视频」「小人在地图上走」「卡通形象走路线」「打卡路线视频」「citywalk 视频」「一日游路线动画」，或丢来一组带位置的旅行照片要做成视频时使用。单张照片找机位用 photo-spot；3D 山体用 map-3d。"
---

# 旅行 vlog travel-vlog

一组旅行照片 + 一张本人照片 → 30–90 秒竖屏手账风 vlog：

| 段落 | 画面 | 声音 |
|---|---|---|
| 开场 | 地球俯冲到第一个机位，落点出标题和日期 | BGM 尤克里里前奏 |
| 全程预览 | 拉远看所有机位，标题「今天去哪了 · N 个机位」 | |
| 每一站 | 卡通小人沿真实路线走（一颠一颠、左右晃、身后扬尘、转向自动翻面），左上「A → B」，右上里程滚动 | 每半拍一声脚步 |
| 到站 | 小人落地小跳 →（叮）→ 换举相机姿势，「咔嚓!」+ 星芒闪光 → 照片啵地弹出：地名 +「第 N 站 · 已走 X km」 | 叮、快门、啵，都在拍点上 |
| 片尾 | 拉回全程，照片一张张掉进照片墙，「N 个机位 · 共走 X km」，小人举相机摇摆 | 每张一声啵，最后叮 |

渲染引擎是 map-motion（`trip` 镜头的 vlog 模式 + `wall` 片尾 + `audio.py` 配乐音效）。本 skill 管流程：照片 → 机位 → 形象 → 检查 → 出片。

## 准备
- map-motion 引擎（同一仓库根目录 `scripts/`）、uv、ffmpeg、高德 key（路线规划、地名）。
- 形象生成：LabNana 图像接口的 key（`LABNANA_API_KEY` 环境变量，或 `travel-vlog/.labnana.env`，或沿用 person-image-studio 的 `.labnana.env`）。没有 key / 积分不足就用内置小人。
- `V=~/.claude/skills/travel-vlog/scripts/vlog.sh`

## 流程

### 1. 收照片，建项目
```sh
mkdir -p ~/Documents/map-motion/<项目名>/src && cp 照片… ~/Documents/map-motion/<项目名>/src/
```
**要原图**：聊天里粘贴的、截图、微信传过的照片没有 GPS。iPhone：照片 App → 选中 → 分享 →「选项」打开「位置」，或「导出未修改的原件」（HEIC 也能用）。

### 2. 照片 → 机位 → spec
```sh
cd ~/Documents/map-motion/<项目名> && $V plan src/* -o vlog.json --title "西湖散步"
```
- 按拍摄时间排序；相距 < 120 m（`--merge`）的照片算同一个机位（每站最多 2 张）
- 每个机位用高德逆地理取最近的景点名（打印出来，**逐行核对**，名字不对直接改 spec 里的 `name`，`photos` 的键要跟着改）
- 直线合计 < 12 km 用步行路线，否则驾车（`--mode` 指定）
- 照片统一转成 `photos/01_1.jpg`…（长边 1600）
- 没 GPS 的照片会列出来：问用户在哪拍的，手写进 `stops`（`{"name", "at": "地名"}` 或坐标）

### 3. 卡通形象
```sh
$V avatar --photo 本人.jpg -o avatar            # AI 按本人照片生成：走路 + 拍照两个姿势，抠成白边贴纸
$V avatar --describe "短发、圆框眼镜、黄色卫衣" -o avatar   # 不传照片，只按文字
$V avatar --builtin "hair=#333,top=#ff8fb1,pants=#5b7bd5" -o avatar   # 内置小人，零成本
```
- **传人像前告诉用户：照片会发给外部 AI 图像服务（LabNana，gpt-image-2）**。用户没同意就用 `--describe` 或 `--builtin`。
- 生成后读 `avatar/preview.png` 看一眼：两个姿势是不是同一个人、朝右、没被裁、白边干净。不行就重跑（每次约 4 积分）或换 `--model gemini-3-pro-image`。
- 也可以用用户自己的卡通图：透明背景 PNG、人物朝右，命名 `walk.png` / `snap.png` 放进 `avatar/`（只有一张就两个都用它）。

### 4. 检查（必做）
```sh
$V check vlog.json
```
每一站「咔嚓」那一刻、照片弹出后、走到一半，以及片尾各抽一帧，**自动质检**（出画、文字互压、文字压照片），出拼图。
- 「质检：通过」→ 只为看整体观感读一次拼图
- 有问题按时刻改：地名太长就改短；照片挡住小人可以接受（照片只停 2 秒左右）

### 5. 出片（后台）
```sh
$V make vlog.json 名字.mp4        # 同时出 名字.gif；2D 渲染快：60 秒片子约 3–5 分钟
```
BGM 和音效自动合成进音轨（原创，无版权问题）。

### 6. 交付
说清：文件位置、时长、几个机位、总里程（高德步行/驾车路线距离，不是 GPS 轨迹）；哪些机位是推测/手填的；形象是 AI 生成还是内置；BGM 是程序合成的原创曲。

## spec 里能改的
| 位置 | 字段 | 说明 |
|---|---|---|
| 顶层 | `style` | 缺省 `amap-journal`（高德街道底图 + 纸纹 + 手写字）；也可 `amap`、`amap-sepia`、`satellite` |
| 顶层 | `music` | `{"bpm": 120, "seed": 1}` 合成 BGM（换 `seed` 换旋律和和弦走向，bpm 100–132 都欢快）；`{"file": "歌.mp3", "bpm": 118}` 用自己的歌（有 bpm 才踩拍点）；`"volume"` 音量 |
| trip | `stops` / `photos` | 机位和每站照片（`{"image", "caption"}`，caption 缺省是地名） |
| trip | `avatar` | `{"walk": "avatar/walk.png", "snap": "avatar/snap.png"}`；去掉就退回普通圆点 |
| trip | `mode` | `walking` / `driving` / `bicycling` |
| trip | `stay` | 每站停留秒数（缺省 3.4，按拍子取整） |
| trip | `drive` | 每段走路的秒数（缺省按距离 2.6+1.6√km，最长 7 秒） |
| trip | `overview` | 先拉远看全程（机位 > 2 时缺省开） |
| wall | `text` / `sub` | 片尾大字（缺省「N 个机位 · 共走 X km」）和小字 |

## 踩过的坑
- 粘贴/微信传过的照片没 GPS → plan 会列出来，问用户。
- 高德地理编码对景点常解析到市中心（「杭州平湖秋月」→ 浙江省杭州市）：plan 用的是逆地理（坐标 → 名字），不受影响；手填地名时核对打印的解析结果。
- 手账矢量样式（`journal`）只能推到 8 级，城市步行要街道级 → vlog 用 `amap-journal`（瓦片）。
- LabNana 返回 `26004 Insufficient credits` ＝积分不足：让用户充值，或先用 `--builtin`。
- 照片有人像时提醒用户这是要公开发布的内容；别把用户照片和形象提交进公开仓库。
