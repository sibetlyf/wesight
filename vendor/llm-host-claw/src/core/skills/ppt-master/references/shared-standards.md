# 共享技术标准

PPT Master 的通用技术约束，消除跨角色文件重复。

---

## 1. SVG 禁用功能黑名单

生成 SVG 时**绝对禁止**使用以下功能 — 如有使用，PPT 导出将失败：

| 禁用功能 | 描述 |
|----------|------|
| `clipPath` | 裁剪路径 |
| `mask` | 遮罩 |
| `<style>` | 嵌入式样式表 |
| `class` | CSS 选择器属性（`<defs>` 内的 `id` 是合法引用，不禁用） |
| 外部 CSS | 外部样式表链接 |
| `<foreignObject>` | 嵌入外部内容 |
| `<symbol>` + `<use>` | 符号引用复用 |
| `textPath` | 路径文字 |
| `@font-face` | 自定义字体声明 |
| `<animate*>` / `<set>` | SVG 动画 |
| `<script>` / 事件属性 | 脚本和交互 |
| `marker` / `marker-end` | 线条端点标记 |
| `<iframe>` | 嵌入框架 |

---

## 2. PPT 兼容性替代方案

| 禁用语法 | 正确替代 |
|----------|----------|
| `fill="rgba(255,255,255,0.1)"` | `fill="#FFFFFF" fill-opacity="0.1"` |
| `<g opacity="0.2">...</g>` | 在每个子元素上单独设置 `fill-opacity` / `stroke-opacity` |
| `<image opacity="0.3"/>` | 在图像后叠加 `<rect fill="背景色" opacity="0.7"/>` 遮罩层 |
| `marker-end` 箭头 | 用 `<polygon>` 绘制三角形箭头 |

**记忆口诀**：PPT 不识别 rgba、组透明度、图像透明度或标记。

---

## 3. 画布格式速查

### 演示文稿

| 格式 | viewBox | 尺寸 | 比例 |
|------|---------|------|------|
| PPT 16:9 | `0 0 1280 720` | 1280x720 | 16:9 |
| PPT 4:3 | `0 0 1024 768` | 1024x768 | 4:3 |

### 社交媒体

| 格式 | viewBox | 尺寸 | 比例 |
|------|---------|------|------|
| 小红书 | `0 0 1242 1660` | 1242x1660 | 3:4 |
| 微信朋友圈 / Instagram 帖子 | `0 0 1080 1080` | 1080x1080 | 1:1 |
| 故事 / 抖音竖屏 | `0 0 1080 1920` | 1080x1920 | 9:16 |

### 营销物料

| 格式 | viewBox | 尺寸 | 比例 |
|------|---------|------|------|
| 微信文章头图 | `0 0 900 383` | 900x383 | 2.35:1 |
| 横版 Banner | `0 0 1920 1080` | 1920x1080 | 16:9 |
| 竖版海报 | `0 0 1080 1920` | 1080x1920 | 9:16 |
| A4 打印 (150dpi) | `0 0 1240 1754` | 1240x1754 | 1:1.414 |

---

## 4. 基本 SVG 规则

- **viewBox** 必须匹配画布尺寸（`width`/`height` 必须匹配 `viewBox`）
- **背景**：使用 `<rect>` 定义页面背景色
- **换行**：使用 `<tspan>` 手动换行；`<foreignObject>` 禁用
- **字体**：仅使用系统字体（微软雅黑、Arial、Calibri 等）；`@font-face` 禁用
- **样式**：仅使用内联样式（`fill="..."` `font-size="..."`）；`<style>` / `class` 禁用（`<defs>` 内的 `id` 合法）
- **颜色**：使用 HEX 值；透明度使用 `fill-opacity` / `stroke-opacity`
- **图像引用**：`<image href="../images/xxx.png" preserveAspectRatio="xMidYMid slice"/>`
- **图标占位符**：`<use data-icon="chunk/name" x="" y="" width="48" height="48" fill="#HEX"/>`（默认库）；或 `tabler-filled/name` / `tabler-outline/name`（选择该库时）。后处理自动嵌入。始终包含库前缀。**一个演示 = 一个库 — 绝不混用。**

### 元素分组（强制）

逻辑相关的元素**必须**用 `<g>` 标签包裹。这会在导出的 PPTX 中生成 PowerPoint 分组，使幻灯片更容易选择、移动和编辑。

> ⚠️ **仅 `<g opacity="...">` 禁用**（见 §2）。普通 `<g>` 用于结构分组是必需的。

**分组单元**：

| 分组单元 | 包含 |
|----------|------|
| 卡片/面板 | 背景矩形 + 阴影 + 图标 + 标题 + 正文 |
| 流程步骤 | 数字圆圈 + 图标 + 标签 + 描述 |
| 列表项 | 项目符号/数字 + 图标 + 标题 + 描述 |
| 图标文字组合 | 图标元素 + 相邻标签 |
| 页面页眉 | 标题 + 副标题 + 装饰 |
| 页面页脚 | 页码 + 品牌 |
| 装饰簇 | 相关装饰形状（圆环、球体、点） |

**示例**：

```xml
<g id="card-benefits-1">
  <rect x="60" y="115" width="565" height="260" rx="20" fill="#FFFFFF" filter="url(#shadow)"/>
  <use data-icon="bolt" x="108" y="163" width="44" height="44" fill="#0071E3"/>
  <text x="105" y="270" font-size="56" font-weight="bold" fill="#0071E3">10×</text>
  <text x="250" y="270" font-size="30" font-weight="bold" fill="#1D1D1F">更快</text>
  <text x="105" y="310" font-size="18" fill="#6E6E73">将生产时间从天缩短到小时。</text>
</g>
```

**命名约定**：在 `<g>` 标签上使用描述性 `id` 属性（如 `card-1`, `step-discover`, `header`, `footer`）。ID 可选但推荐用于可读性。

---

## 5. 后处理流程（3 步）

必须按顺序执行 — 跳过或添加额外标志是禁止的：

```bash
# 1. 将演讲者备注拆分为每页备注文件
python3 scripts/total_md_split.py <项目路径>

# 2. SVG 后处理（图标嵌入、图像裁剪/嵌入、文字扁平化、圆角矩形转路径）
python3 scripts/finalize_svg.py <项目路径>

# 3. 导出 PPTX（从 svg_final/，默认嵌入演讲者备注）
python3 scripts/svg_to_pptx.py <项目路径> -s final
# 默认：生成原生形状（.pptx）+ SVG 参考（_svg.pptx）
```

**禁止**：
- 绝不要用 `cp` 替代 `finalize_svg.py`
- 绝不要直接从 `svg_output/` 导出 — 必须从 `svg_final/` 导出（使用 `-s final`）
- 绝不要添加额外标志如 `--only`

**重新运行规则**：后处理完成后对 `svg_output/` 的任何修改（包括页面修订、添加或删除）都需要重新运行第 2 和第 3 步。仅当 `notes/total.md` 也被修改时才需要重新运行第 1 步。

---

## 6. 阴影与叠加技术

> `<mask>` 元素和 `<image opacity="...">` 禁用。始终使用堆叠 `<rect>` 或渐变叠加替代（见 §2）。

### 阴影

#### 滤镜柔阴影 — 推荐

最适合：卡片、浮动面板、提升元素。`svg_to_pptx` 转换器自动将 `feGaussianBlur` + `feOffset` 转换为原生 PPTX `<a:outerShdw>`。

```xml
<defs>
  <filter id="softShadow" x="-15%" y="-15%" width="140%" height="140%">
    <feGaussianBlur in="SourceAlpha" stdDeviation="12"/>
    <feOffset dx="0" dy="6" result="offsetBlur"/>
    <feFlood flood-color="#000000" flood-opacity="0.15" result="shadowColor"/>
    <feComposite in="shadowColor" in2="offsetBlur" operator="in" result="shadow"/>
    <feMerge>
      <feMergeNode in="shadow"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
</defs>
<rect x="60" y="60" width="400" height="240" rx="12" fill="#FFFFFF" filter="url(#softShadow)"/>
```

推荐参数：
```
stdDeviation:   10–16    （小 = 更清晰，大 = 更柔和）
flood-opacity:  0.12–0.20  （太低在 PPTX 中会不可见）
dy:             4–8      （垂直 > 水平，自然顶光）
dx:             0–2
```

#### 彩色阴影

最适合：强调按钮、品牌色卡片。使用元素自身的颜色族而非黑色。

```xml
<filter id="colorShadow" x="-15%" y="-15%" width="140%" height="140%">
  <feGaussianBlur in="SourceAlpha" stdDeviation="10"/>
  <feOffset dx="0" dy="6" result="offsetBlur"/>
  <feFlood flood-color="#1A73E8" flood-opacity="0.20" result="shadowColor"/>
  <feComposite in="shadowColor" in2="offsetBlur" operator="in" result="shadow"/>
  <feMerge>
    <feMergeNode in="shadow"/>
    <feMergeNode in="SourceGraphic"/>
  </feMerge>
</filter>
```

将 `flood-color` 替换为元素的品牌色；保持 `flood-opacity` 在 0.15–0.25 之间。

#### 发光效果

最适合：标题高亮、关键指标、主文字。转换器自动将无 `feOffset` 的 `feGaussianBlur` 转换为原生 PPTX `<a:glow>`。

```xml
<defs>
  <filter id="titleGlow" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur in="SourceAlpha" stdDeviation="6" result="blur"/>
    <feFlood flood-color="#1A73E8" flood-opacity="0.45" result="glowColor"/>
    <feComposite in="glowColor" in2="blur" operator="in" result="glow"/>
    <feMerge>
      <feMergeNode in="glow"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
</defs>
<text x="640" y="360" text-anchor="middle" font-size="48" fill="#1A73E8" filter="url(#titleGlow)">关键洞察</text>
```

推荐参数：
```
stdDeviation:   4–8      （小 = 微妙，大 = 显著）
flood-color:    品牌色或强调色（非黑色）
flood-opacity:  0.35–0.55  （比阴影更强以确保可见）
```

**与阴影的关键区别**：无 `<feOffset>` 元素（或 dx=0/dy=0）。转换器用此区分发光与阴影。

#### 层叠矩形阴影 — 高兼容性后备

最适合：与旧版 PowerPoint 的最大兼容性。在主卡片后堆叠 2–3 个半透明矩形：

```xml
<!-- 阴影层（从后往前，最大偏移优先） -->
<rect x="68" y="72" width="400" height="240" rx="16" fill="#000000" fill-opacity="0.03"/>
<rect x="65" y="69" width="400" height="240" rx="14" fill="#000000" fill-opacity="0.05"/>
<rect x="62" y="66" width="400" height="240" rx="12" fill="#1A73E8" fill-opacity="0.04"/>
<!-- 主卡片 -->
<rect x="60" y="60" width="400" height="240" rx="12" fill="#FFFFFF"/>
```

### 图像叠加

#### 线性渐变叠加 — 最常用

最适合：图像+文字页面。渐变方向应与文字位置匹配（文字在左 → 渐变向左变暗）。

```xml
<image href="..." x="0" y="0" width="1280" height="720" preserveAspectRatio="xMidYMid slice"/>
<defs>
  <linearGradient id="imgOverlay" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%"   stop-color="#1A1A2E" stop-opacity="0.85"/>
    <stop offset="55%"  stop-color="#1A1A2E" stop-opacity="0.30"/>
    <stop offset="100%" stop-color="#1A1A2E" stop-opacity="0"/>
  </linearGradient>
</defs>
<rect x="0" y="0" width="1280" height="720" fill="url(#imgOverlay)"/>
```

#### 底部渐变条

最适合：封面幻灯片和底部标题的全图像页面。

```xml
<defs>
  <linearGradient id="bottomBar" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%"   stop-color="#000000" stop-opacity="0"/>
    <stop offset="100%" stop-color="#000000" stop-opacity="0.72"/>
  </linearGradient>
</defs>
<rect x="0" y="380" width="1280" height="340" fill="url(#bottomBar)"/>
```

#### 径向渐变叠加 — 暗角效果

最适合：全屏氛围幻灯片；将注意力吸引到中心。

```xml
<defs>
  <radialGradient id="vignette" cx="50%" cy="50%" r="70%">
    <stop offset="0%"   stop-color="#000000" stop-opacity="0"/>
    <stop offset="100%" stop-color="#000000" stop-opacity="0.58"/>
  </radialGradient>
</defs>
<rect x="0" y="0" width="1280" height="720" fill="url(#vignette)"/>
```

#### 品牌色叠加

最适合：需要强烈视觉品牌识别的幻灯片。

```xml
<defs>
  <linearGradient id="brandOverlay" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%"   stop-color="#005587" stop-opacity="0.80"/>
    <stop offset="100%" stop-color="#005587" stop-opacity="0.10"/>
  </linearGradient>
</defs>
<rect x="0" y="0" width="1280" height="720" fill="url(#brandOverlay)"/>
```

### 速查表

| 场景 | 推荐技术 | 避免 |
|------|----------|------|
| 卡片/面板阴影 | 滤镜柔阴影（`flood-opacity` ≤ 0.12） | 硬黑阴影 |
| 强调/CTA 按钮 | 彩色阴影（同色系） | 通用灰阴影 |
| 标题/指标高亮 | 发光滤镜（品牌色，无偏移） | 正文文字过度使用 |
| 图像上的文字 | 线性渐变叠加（方向匹配文字侧） | 整图统一平铺透明度 |
| 封面/全图像幻灯片 | 底部渐变条 + 品牌色 | 纯黑叠加 |
| 氛围/主视觉幻灯片 | 径向暗角 | 未处理的原始图像 |
| 需要最大 PPT 兼容性 | 层叠矩形阴影 | 基于滤镜的阴影 |

---

## 7. 描边、文字与形状效果

### stroke-dasharray — 虚线/点线

转换为原生 PPTX `<a:prstDash>`。使用预设图案获得最佳效果：

| SVG 值 | PPTX 预设 | 最适合 |
|--------|-----------|--------|
| `4,4` | Dash | 通用虚线、分隔符 |
| `2,2` | Dot (sysDot) | 微妙点状边框、占位符轮廓 |
| `8,4` | Long dash | 时间线连接器、流程箭头 |
| `8,4,2,4` | Long dash-dot | 技术图纸、尺寸线 |

```xml
<rect x="60" y="60" width="400" height="240" rx="12"
  fill="none" stroke="#999999" stroke-width="2" stroke-dasharray="4,4"/>

<line x1="100" y1="360" x2="1180" y2="360"
  stroke="#CCCCCC" stroke-width="1" stroke-dasharray="2,2"/>
```

### stroke-linejoin

控制线段在拐角处的连接方式。支持的值转换为原生 PPTX 线条连接类型：

| SVG 值 | PPTX 等效 | 最适合 |
|--------|-----------|--------|
| `round` | Round join | 平滑折线图表、有机形状 |
| `bevel` | Bevel join | 技术图表 |
| `miter` | Miter join（默认） | 尖角矩形、箭头 |

```xml
<polyline points="100,200 200,100 300,200" fill="none"
  stroke="#1A73E8" stroke-width="3" stroke-linejoin="round"/>
```

### text-decoration

支持的文本装饰转换为原生 PPTX 文本格式：

| SVG 值 | PPTX 等效 | 最适合 |
|--------|-----------|--------|
| `underline` | Single underline | 强调、链接、关键术语 |
| `line-through` | Strikethrough | 已移除项、前后对比 |

```xml
<text x="100" y="200" font-size="20" fill="#333333" text-decoration="underline">重要术语</text>

<!-- 每 tspan 装饰 -->
<text x="100" y="240" font-size="18" fill="#333333">
  普通文字 <tspan text-decoration="line-through" fill="#999999">旧值</tspan> 新值
</text>
```

### 渐变填充 — linearGradient & radialGradient

在 `<defs>` 中定义并通过 `fill="url(#id)"` 引用的渐变转换为原生 PPTX `<a:gradFill>`。将它们用作形状填充（不仅是叠加）以获得抛光表面。

**线性渐变** — 最适合按钮、标题栏、背景面板：

```xml
<defs>
  <linearGradient id="btnGrad" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#1A73E8"/>
    <stop offset="100%" stop-color="#0D47A1"/>
  </linearGradient>
</defs>
<rect x="540" y="600" width="200" height="48" rx="24" fill="url(#btnGrad)"/>
```

**径向渐变** — 最适合聚光灯背景、圆形强调：

```xml
<defs>
  <radialGradient id="spotBg" cx="50%" cy="50%" r="70%">
    <stop offset="0%" stop-color="#1A73E8" stop-opacity="0.15"/>
    <stop offset="100%" stop-color="#1A73E8" stop-opacity="0"/>
  </radialGradient>
</defs>
<circle cx="640" cy="360" r="300" fill="url(#spotBg)"/>
```

### transform: rotate — 元素旋转

旋转转换为原生 PPTX `<a:xfrm rot="...">`。支持所有元素类型：`rect`, `circle`, `ellipse`, `line`, `path`, `polygon`, `polyline`, `image`, `text`。

```xml
<!-- 旋转装饰元素 -->
<rect x="100" y="100" width="60" height="60" fill="#1A73E8" fill-opacity="0.1"
  transform="rotate(45, 130, 130)"/>

<!-- 旋转文字标签 -->
<text x="50" y="400" font-size="14" fill="#999999"
  transform="rotate(-90, 50, 400)">Y 轴标签</text>
```

**语法**：`rotate(angle)` 或 `rotate(angle, cx, cy)` 其中 `cx,cy` 是旋转中心。正角度顺时针旋转。

### 弧线路径 — 环形/饼图

用 `<path>` 绘制环形或饼图扇区时，弧线路径端点坐标必须使用三角函数精确计算。**绝不要估计或近似弧线路径端点** — 即使小错误也会产生 wildly incorrect 形状。

**计算公式**（中心 `cx,cy`，半径 `r`，角度 `θ` 度）：
```
x = cx + r × cos(θ × π / 180)
y = cy + r × sin(θ × π / 180)
```

**关键规则**：
1. 从 **-90°**（12 点位置）开始顺时针
2. 每个扇区跨度 `百分比 × 360°`
3. 扇区 > 180° 时使用 **large-arc flag = 1**，否则 **0**
4. sweep-direction = 1（顺时针）外弧，0（逆时针）内弧返回
5. **始终验证**所有扇区角度之和等于 360°，且最后一个扇区的终点与第一个扇区的起点匹配

**示例 — 75% 环形扇区**（中心 400,400，外半径 180，内半径 100）：
```
起始角度: -90°    → 外(400, 220), 内(400, 300)
结束角度: -90+270=180° → 外(220, 400), 内(300, 400)
Large-arc flag: 1 (270° > 180°)

<path d="M 400,220 A 180,180 0 1,1 220,400 L 300,400 A 100,100 0 1,0 400,300 Z"/>
```

### 斜线上的多边形箭头

使用 `<polygon>` 三角形作为箭头（因为 `marker-end` 禁用）时，**水平或垂直线**上的箭头可以使用简单点偏移。但**斜线**上的箭头必须旋转三角形顶点以匹配线条方向。

**方法**：使用线条的方向向量计算三角形点：

```
给定从 (x1,y1) 到 (x2,y2) 的线：
1. 方向向量: dx = x2-x1, dy = y2-y1
2. 归一化: len = √(dx²+dy²), ux = dx/len, uy = dy/len
3. 垂直: px = -uy, py = ux
4. 箭头尖端 = (x2, y2)
5. 后点 1 = (x2 - ux×12 + px×5,  y2 - uy×12 + py×5)
6. 后点 2 = (x2 - ux×12 - px×5,  y2 - uy×12 - py×5)
```

**示例 — 从 (260,310) 到 (370,430) 的斜线**：
```
dx=110, dy=120, len≈162.8, ux=0.676, uy=0.737
px=-0.737, py=0.676
尖端: (370, 430)
后1: (370-8.1-3.7, 430-8.8+3.4) = (358.2, 424.6)
后2: (370-8.1+3.7, 430-8.8-3.4) = (365.6, 417.8)

<polygon points="370,430 365.6,417.8 358.2,424.6" fill="#C8A96E"/>
```

⚠️ **绝不要在斜线上使用固定的向下/向右三角形** — 箭头会指向错误方向。

---

## 8. 项目目录结构

```
project/
├── svg_output/    # 原始 SVG（执行者输出，包含占位符）
├── svg_final/     # 后处理后的最终 SVG（finalize_svg.py 输出）
├── images/        # 图像资源（用户提供 + AI 生成）
├── notes/         # 演讲者备注（与 SVG 名称匹配的 .md 文件）
│   └── total.md   # 完整演讲者备注文档（拆分前）
├── templates/     # 项目模板（如有）
└── *.pptx         # 导出的 PPT 文件
```
