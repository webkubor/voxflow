# VoxFlow 音乐封面提示词模板

> **用法**：把 `{占位符}` 替换成实际歌曲信息，喂给 museav gen 出图。
> 跑生成前用 `scripts/gen_cover_prompt.py` 自动填参。

## 模板正文

```
1:1 正方形（3000×3000，85% JPEG，< 5MB），
{platform}歌单封面。35mm 焦距 f/2.0 浅景深摄影。

[主体]
画面中央略偏左，{character}，
穿{clothing}，佩戴{accessory}。
微仰头 15°，{pose}，{expression}。

[姿势 / 神态]
完全松弛的{mood_state}状态，肩膀下沉，呼吸感可见。
不看镜头，不摆拍，像被偶然抓拍的真实瞬间。

[机位]
{angle}，{framing}。
35mm 等效焦距，f/2.0，焦点在眼睛，背景柔和虚化。

[环境]
{scene}，{time_desc}。
{environment_detail}。
整体色调：{color_palette}。

[光线]
自然{light_type}（来自{light_dir}），
{light_effect}，皮肤保持通透 + 真实肌理（可见毛孔、细绒毛）。
不磨皮，不美颜，不塑料。

[质感]
Shot on Fuji X-T5 + Kodak Portra 400 胶片模拟。
轻微胶片颗粒，柔和高光溢出，自然镜头炫光 + 空气透视。

[装饰元素]
{decoration}

[文字版式]
主标题「{title}」放在画面中央偏上 1/3 处（距上边缘 25%），
{title_font}，字号约占画面高度 1/8，
距画面边缘 ≥ 10%（圆形裁切安全区）。
副标题「{subtitle}」位于主标题下方 1 个标题高度处，
{subtitle_font}，字距 200，字号约为主标题 1/3。

[风格锚点]
参考：{style_reference}

[关键词]
{keywords_en}

[避免]
血、真实心脏、医学插画、医院元素、赛博朋克、霓虹红光、
暗黑背景、AI 塑料皮、磨皮美颜、影楼摄影、文字过多、
人物直视镜头、波形屏幕、网格坐标、刻度数字。
```

## 占位符说明

| 占位符 | 含义 | 示例 |
|---|---|---|
| `{platform}` | 上架平台 | `汽水音乐` / `网易云` / `QQ 音乐` |
| `{title}` | 主标题中文 | `心脏跳动` |
| `{subtitle}` | 副标题英文（大写） | `HEARTBEAT` |
| `{character}` | 人物设定 | `年轻东亚女性（约 22-25 岁）` |
| `{clothing}` | 服装 | `干净奶油白棉质 T 恤` |
| `{accessory}` | 关键配饰 | `白色头戴式耳机` |
| `{pose}` | 姿势 | `闭眼，长发被晚风自然吹向画面右侧` |
| `{expression}` | 表情 | `嘴角微微上扬，像在微笑哼歌` |
| `{mood_state}` | 情绪状态 | `听歌入迷` / `奔跑追逐` / `凝望远方的释然` |
| `{angle}` | 镜头角度 | `平视略仰拍 5°` / `俯拍 15°` |
| `{framing}` | 画面取景 | `中景（腰部以上）` / `全身` |
| `{scene}` | 场景 | `城市天台` / `海边公路` / `深夜便利店门口` |
| `{time_desc}` | 时间 | `傍晚蓝调时刻` / `清晨 6 点金色时刻` / `深夜雨后` |
| `{environment_detail}` | 环境细节 | `天空中漂浮少量云被夕阳染成淡粉、奶橘色；远处建筑虚化为散景光斑` |
| `{color_palette}` | 主色调 | `蓝白为主 + 极少量暖粉橙点缀` |
| `{light_type}` | 光源类型 | `夕阳侧逆光` / `清晨金色散射光` / `深夜便利店霓虹散光` |
| `{light_dir}` | 光源方向 | `画面右上方 30°` / `正前方略高 45°` |
| `{light_effect}` | 光效 | `发丝边缘金色轮廓光 + 皮肤通透保留肌理` |
| `{decoration}` | 装饰元素 | `画面左下到右下细线手绘波动曲线，象征音乐让心跳被感知` |
| `{title_font}` | 主标题字体 | `白色思源宋体 Bold` / `白色小雅宋 Heavy` |
| `{subtitle_font}` | 副标题字体 | `白色 Helvetica Neue Light` |
| `{style_reference}` | 风格参考摄影师 | `滨田英明 家庭日记 / 上田义彦 静谧人像` |
| `{keywords_en}` | 英文关键词（逗号分隔） | `Japanese editorial photography, cinematic summer dusk, ...` |

## 常用配置预设（覆盖大部分场景）

### 治愈系傍晚
- `{time_desc}` = `傍晚蓝调时刻`
- `{light_type}` = `夕阳侧逆光`
- `{color_palette}` = `蓝白为主 + 极少量暖粉橙点缀`
- `{decoration}` = `细线手绘波动曲线，象征音乐让心跳被感知`
- `{style_reference}` = `滨田英明 家庭日记`

### 热血系正午
- `{time_desc}` = `正午烈日`
- `{light_type}` = `顶光强对比`
- `{color_palette}` = `高饱和红黄 + 黑色阴影对比`
- `{decoration}` = `无装饰，纯人物 + 光影`
- `{style_reference}` = `森山大道 街头摄影`

### 伤感深夜
- `{time_desc}` = `深夜雨后`
- `{light_type}` = `便利店霓虹散光`
- `{color_palette}` = `冷蓝 + 远处暖色霓虹散景`
- `{decoration}` = `无装饰，单人独处`
- `{style_reference}` = `上田义彦 静谧人像`

### 抖音热门卡点
- `{time_desc}` = `深夜 club`
- `{light_type}` = `频闪彩色光`
- `{color_palette}` = `黑底 + 霓虹粉/紫/青`
- `{decoration}` = `音乐节拍点或闪烁光斑`
- `{style_reference}` = `Tim Walker 时尚摄影`

## 重要规则

1. **不要自动跑 museav gen** —— `museav gen` 花钱，需要用户明确同意才执行
2. **不要去掉「避免」清单** —— 那是质量保险，去掉必出俗气封面
3. **每首歌必须填所有必填占位符** —— 留空会产生默认值导致风格漂移
4. **主标题字体指定具体名** —— 不要写「好看的字体」，AI 会乱选
5. **场景要具体到「在哪、什么时间、什么天气」** —— 模糊描述 = 通用网红照
