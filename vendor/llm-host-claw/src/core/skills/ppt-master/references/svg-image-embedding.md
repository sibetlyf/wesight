> 通用技术约束参见 shared-standards-zh.md。

# SVG 图片嵌入指南

向 SVG 文件添加图片的技术规范和推荐工作流程。

---

## 图片资源列表格式

在设计规范与内容大纲中定义；每张图片带有状态标注。如果图片方案包含"B) 用户提供"，必须在策略师完成八项确认后立即运行 `analyze_images.py`，并在输出设计规范前完成列表。

```markdown
| 文件名 | 尺寸 | 用途 | 状态 | 生成描述 |
|--------|------|------|------|----------|
| cover_bg.png | 1280x720 | 封面背景 | 待生成 | 现代科技抽象背景，深蓝渐变 |
| product.png | 600x400 | 第3页 | 已有 | - |
| team.png | 600x400 | 第5页 | 占位符 | 团队协作场景（稍后添加） |
```

### 三种状态类型

| 状态 | 含义 | 执行器处理方式 |
|------|------|----------------|
| **待生成** | 需要 AI 生成，已有描述 | 先生成图片到 `images/`，然后用 `<image>` 引用 |
| **已有** | 用户已有图片 | 放入 `images/`，用 `<image>` 引用 |
| **占位符** | 尚未处理 | 使用虚线边框占位符；稍后替换 |

---

## 工作流程

```
1. 策略师定义图片需求 → 添加图片资源列表，标注每个状态
2. 图片准备（待生成/已有）→ 放入 project/images/
3. 执行器生成 SVG（svg_output/）
   ├── 已有/待生成 → <image href="../images/xxx.png" .../>
   └── 占位符 → 虚线边框 + 描述文字
4. 预览：python3 -m http.server -d <project_path> 8000 → /svg_output/<filename>.svg
5. 后处理与导出
   ├── python3 scripts/finalize_svg.py <project_path>
   └── python3 scripts/svg_to_pptx.py <project_path> -s final
```

> 推荐：生成阶段保持 `svg_output/` 中的外部引用。通过 `finalize_svg.py` 后处理自动将图片嵌入到 `svg_final/`，然后从 `svg_final/` 导出 PPTX。

---

## 外部引用 vs Base64 嵌入

| 方法 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **外部引用** | 文件小，迭代快，易于替换 | 预览需要从项目根目录启动 HTTP 服务器 | `svg_output/` 开发阶段 |
| **Base64 嵌入** | 文件自包含，导出稳定 | 文件大 | `svg_final/` 交付阶段 |

---

## 方法 1：外部引用（生成阶段推荐）

### 语法

```xml
<image href="../images/image.png" x="0" y="0" width="1280" height="720"
       preserveAspectRatio="xMidYMid slice"/>
```

### 关键属性

| 属性 | 说明 | 示例 |
|------|------|------|
| `href` | 图片路径（相对或绝对） | `"../images/cover.png"` |
| `x`, `y` | 图片左上角位置 | `x="0" y="0"` |
| `width`, `height` | 图片显示尺寸 | `width="1280" height="720"` |
| `preserveAspectRatio` | 缩放模式 | `"xMidYMid slice"` |

### preserveAspectRatio 常用值

| 值 | 效果 |
|----|------|
| `xMidYMid slice` | 居中裁剪（类似 CSS `cover`） |
| `xMidYMid meet` | 完整显示（类似 CSS `contain`） |
| `none` | 拉伸填充，不保持宽高比 |

### 预览方法

浏览器安全限制阻止直接从打开的 SVG 加载外部图片。从项目根目录启动 HTTP 服务器：

```bash
python3 -m http.server -d <project_path> 8000
# 访问 http://localhost:8000/svg_output/your_file.svg
```

---

## 方法 2：Base64 嵌入（交付阶段推荐）

### 语法

```xml
<image href="data:image/png;base64,iVBORw0KGgo..." x="0" y="0" width="1280" height="720"/>
```

### MIME 类型

| MIME 类型 | 文件格式 |
|-----------|----------|
| `image/png` | PNG |
| `image/jpeg` | JPG/JPEG |
| `image/gif` | GIF |
| `image/webp` | WebP |
| `image/svg+xml` | SVG |

---

## 转换流程

### 推荐：使用 finalize_svg.py（统一流程）

```bash
python3 scripts/finalize_svg.py <project_path>         # 图标、图片、文字、圆角矩形 —— 一次完成
python3 scripts/svg_to_pptx.py <project_path> -s final  # 从最终版本导出 PPTX
```

### 独立：embed_images.py（高级用法）

不运行完整流程，处理特定 SVG：

```bash
python3 scripts/svg_finalize/embed_images.py <svg_file>                         # 单文件
python3 scripts/svg_finalize/embed_images.py <project_path>/svg_output/*.svg    # 批量
python3 scripts/svg_finalize/embed_images.py --dry-run <project_path>/svg_output/*.svg  # 预览
```

---

## 最佳实践

### 图片优化

嵌入前压缩图片以减小文件大小：

```bash
convert input.png -quality 85 -resize 1920x1080\> output.png  # ImageMagick
pngquant --quality=65-80 input.png -o output.png               # pngquant（推荐）
```

### 文件组织

```
project/
├── images/            # 图片资源
├── sources/           # 源文件及其配套图片
│   └── article_files/
├── svg_output/        # 原始版本（外部引用）
└── svg_final/         # 最终版本（图片嵌入）
```

### 圆角处理（禁止使用 clipPath）

由于 `clipPath` 与 PPT 不兼容，禁止使用裁剪路径实现图片圆角。替代方案：
- 图片生成时处理圆角（导出带圆角的 PNG）
- 或在边缘叠加同尺寸圆角矩形（视觉模拟）

---

## 常见问题

**Q：直接打开 SVG 看不到图片？**
浏览器安全策略阻止跨目录请求。从项目根目录启动 HTTP 服务器，或先运行 `finalize_svg.py` 然后从 `svg_final/` 查看。

**Q：Base64 文件太大？**
压缩原图，使用 JPEG 格式，降低分辨率（匹配实际显示尺寸）。

**Q：如何反向提取 Base64 图片？**
```bash
base64 -d image.b64 > image.png
```
