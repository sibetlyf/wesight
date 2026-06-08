---
name: ppt-master
description: >
  AI 驱动的多格式 SVG 内容生成系统。通过多角色协作，将源文档（PDF/DOCX/URL/Markdown）
  转换为高质量的 SVG 页面并导出为 PPTX。当用户要求"创建 PPT"、"制作演示文稿"、
  "生成PPT"、"做PPT"、"制作演示文稿"或提到"ppt-master"时使用。
---

# PPT Master 技能

> AI 驱动的多格式 SVG 内容生成系统。通过多角色协作将源文档转换为高质量的 SVG 页面并导出为 PPTX。

**核心流程**：`源文档 → 创建项目 → 模板选项 → 策略师 → [图像生成器] → 执行者 → 后处理 → 导出`

> [!CAUTION]
> ## 🚨 全局执行纪律（强制）
>
> **本工作流程是严格的串行流程。以下规则具有最高优先级——违反任何一条都构成执行失败：**
>
> 1. **串行执行** — 步骤必须按顺序执行；每个步骤的输出是下一个步骤的输入。一旦满足先决条件，非阻塞的相邻步骤可以连续进行，无需等待用户说"继续"
> 2. **进入前检查** — 每个步骤顶部列出的先决条件（🚧 门槛）必须在开始该步骤前验证
> 3. **禁止投机执行** — 禁止为后续步骤"预先准备"内容（例如，在策略师阶段编写 SVG 代码）
> 4. **禁止子智能体 SVG 生成** — 执行者第 6 步的 SVG 生成依赖于上下文，必须由当前主智能体从头到尾完成。禁止将幻灯片 SVG 生成委托给子智能体
> 5. **仅顺序页面生成** — 在执行者第 6 步中，确认全局设计上下文后，执行者必须在一个连续的主智能体上下文中逐页顺序生成页面。不要将第 6 步分成每批 5 页的页面批次

> [!IMPORTANT]
> ## 🌐 语言与沟通规则
>
> - **回复语言**：始终与用户输入和提供的源材料语言保持一致。例如，如果用户用中文提问，用中文回复；如果源材料是英文，用英文回复。
> - **显式覆盖**：如果用户明确要求特定语言（例如，"请用英文回答"或"Reply in Chinese"），则使用该语言。
> - **模板格式**：无论对话语言如何，`design_spec.md` 文件必须始终遵循其原始的英文模板结构（章节标题、字段名称）。模板内的内容值可以使用用户的语言。


## 主流程脚本

| 脚本 | 用途 |
|------|------|
| `${SKILL_DIR}/scripts/pdf_to_md.py` | PDF 转 Markdown |
| `${SKILL_DIR}/scripts/doc_to_md.py` | 通过 Pandoc 将文档转为 Markdown（DOCX、EPUB、HTML、LaTeX、RST 等） |
| `${SKILL_DIR}/scripts/ppt_to_md.py` | PowerPoint 转 Markdown |
| `${SKILL_DIR}/scripts/web_to_md.py` | 网页转 Markdown |
| `${SKILL_DIR}/scripts/web_to_md.cjs` | 微信/高安全性网站转 Markdown |
| `${SKILL_DIR}/scripts/project_manager.py` | 项目初始化/验证/管理 |
| `${SKILL_DIR}/scripts/analyze_images.py` | 图像分析 |
| `${SKILL_DIR}/scripts/image_gen.py` | AI 图像生成（多提供商） |
| `${SKILL_DIR}/scripts/svg_quality_checker.py` | SVG 质量检查 |
| `${SKILL_DIR}/scripts/total_md_split.py` | 演讲者备注拆分 |
| `${SKILL_DIR}/scripts/finalize_svg.py` | SVG 后处理（统一入口） |
| `${SKILL_DIR}/scripts/svg_to_pptx.py` | 导出为 PPTX |

完整的工具文档，请参阅 `${SKILL_DIR}/scripts/README.md`。

## 模板索引

| 索引 | 路径 | 用途 |
|------|------|------|
| 布局模板 | `${SKILL_DIR}/templates/layouts/layouts_index.json` | 查询可用的页面布局模板 |
| 图表模板 | `${SKILL_DIR}/templates/charts/charts_index.json` | 查询可用的图表 SVG 模板 |
| 图标库 | `${SKILL_DIR}/templates/icons/` | 按需搜索图标：`ls templates/icons/<library>/ | grep <keyword>`（库：`chunk/`、`tabler-filled/`、`tabler-outline/`） |

## 独立工作流

| 工作流 | 路径 | 用途 |
|--------|------|------|
| `create-template` | `workflows/create-template.md` | 独立模板创建工作流 |

---

## 工作流程

### 第 1 步：源内容处理

🚧 **门槛**：用户已提供源材料（PDF / DOCX / EPUB / URL / Markdown 文件 / 文本描述 / 对话内容——任何形式均可接受）。

当用户提供非 Markdown 内容时，立即转换：

| 用户提供 | 命令 |
|---------|------|
| PDF 文件 | `python3 ${SKILL_DIR}/scripts/pdf_to_md.py <文件>` |
| DOCX / Word / Office 文档 | `python3 ${SKILL_DIR}/scripts/doc_to_md.py <文件>` |
| PPTX / PowerPoint 演示文稿 | `python3 ${SKILL_DIR}/scripts/ppt_to_md.py <文件>` |
| EPUB / HTML / LaTeX / RST / 其他 | `python3 ${SKILL_DIR}/scripts/doc_to_md.py <文件>` |
| 网页链接 | `python3 ${SKILL_DIR}/scripts/web_to_md.py <URL>` |
| 微信 / 高安全性网站 | `node ${SKILL_DIR}/scripts/web_to_md.cjs <URL>` |
| Markdown | 直接读取 |

**✅ 检查点 — 确认源内容已准备就绪，进入第 2 步。**

---

### 第 2 步：项目初始化

🚧 **门槛**：第 1 步完成；源内容已准备就绪（Markdown 文件、用户提供的文本，或对话中描述的需求均有效）。

```bash
python3 ${SKILL_DIR}/scripts/project_manager.py init <项目名称> --format <格式>
```

格式选项：`ppt169`（默认）、`ppt43`、`xhs`、`story` 等。完整格式列表，请参阅 `references/canvas-formats.md`。

导入源内容（根据情况选择）：

| 情况 | 操作 |
|------|------|
| 有源文件（PDF/MD等） | `python3 ${SKILL_DIR}/scripts/project_manager.py import-sources <项目路径> <源文件...> --move` |
| 用户直接在对话中提供文本 | 无需导入——内容已在对话上下文中；后续步骤可直接引用 |

> ⚠️ **必须使用 `--move`**：所有源文件（原始 PDF / MD / 图像）必须**移动**（而非复制）到 `sources/` 进行归档。
> - 第 1 步生成的 Markdown 文件、原始 PDF、原始 MD——**所有**文件必须通过 `import-sources --move` 移动到项目中
> - 中间产物（例如 `_files/` 目录）由 `import-sources` 自动处理
> - 执行后，源文件不再存在于原始位置

**✅ 检查点 — 确认项目结构创建成功，`sources/` 包含所有源文件，转换后的材料已准备就绪。进入第 3 步。**

---

### 第 3 步：模板选择

🚧 **门槛**：第 2 步完成；项目目录结构已准备就绪。

AI 根据当前 PPT 主题和内容，直接推荐最合适的模板或选择自由设计：

1. 查询 `${SKILL_DIR}/templates/layouts/layouts_index.json` 列出可用模板
2. 根据主题和内容选择最合适的模板
3. 将模板文件复制到项目目录：
```bash
cp ${SKILL_DIR}/templates/layouts/<模板名称>/*.svg <项目路径>/templates/
cp ${SKILL_DIR}/templates/layouts/<模板名称>/design_spec.md <项目路径>/templates/
cp ${SKILL_DIR}/templates/layouts/<模板名称>/*.png <项目路径>/images/ 2>/dev/null || true
cp ${SKILL_DIR}/templates/layouts/<模板名称>/*.jpg <项目路径>/images/ 2>/dev/null || true
```

> 要创建新的全局模板，请阅读 `workflows/create-template.md`

**✅ 检查点 — 模板已确定。进入第 4 步。**

---

### 第 4 步：策略师阶段（强制——不能跳过）

🚧 **门槛**：第 3 步完成；模板已确定。

阅读角色定义：
```
Read references/strategist.md
```

AI 直接根据内容生成八项设计规范（有关模板结构，请参阅 `templates/design_spec_reference.md`）：

1. 画布格式
2. 页数范围
3. 目标受众
4. 风格目标
5. 配色方案
6. 图标使用方法
7. 字体计划
8. 图像使用方法

如果用户提供了图像，在**输出设计规范之前**运行分析脚本（不要直接读取/打开图像文件——仅使用脚本输出）：
```bash
python3 ${SKILL_DIR}/scripts/analyze_images.py <项目路径>/images
```

> ⚠️ **图像处理规则**：AI 绝不能直接读取、打开或查看图像文件（`.jpg`、`.png` 等）。所有图像信息必须来自 `analyze_images.py` 脚本输出或设计规范的图像资源列表。

**输出**：`<项目路径>/design_spec.md`

**✅ 检查点 — 设计规范生成完成，自动进入下一步**：
```markdown
## ✅ 策略师阶段完成
- [x] 八项设计规范已生成
- [x] 设计规范和内容大纲已生成
- [ ] **下一步**：自动进入 [图像生成器 / 执行者] 阶段
```

---

### 第 5 步：图像生成器阶段（条件性）

🚧 **门槛**：第 4 步完成；设计规范已生成。

> **触发条件**：图像方法包括"AI 生成"。如果未触发，直接跳到第 6 步（第 6 步的门槛仍必须满足）。

阅读 `references/image-generator.md`

1. 从设计规范中提取所有状态为"待生成"的图像
2. 生成提示词文档 → `<项目路径>/images/image_prompts.md`
3. 生成图像（推荐使用 CLI 工具）：
   ```bash
   python3 ${SKILL_DIR}/scripts/image_gen.py "提示词" --aspect_ratio 16:9 -o <项目路径>/images 
   ```

**✅ 检查点 — 确认所有图像已准备就绪，进入第 6 步**：
```markdown
## ✅ 图像生成器阶段完成
- [x] 提示词文档已创建
- [x] 所有图像已保存到 images/
```

---

### 第 6 步：执行者阶段

🚧 **门槛**：第 4 步完成（如果触发，还包括第 5 步）；所有先决条件交付物已准备就绪。

根据所选样式阅读角色定义：
```
Read references/executor-base.md          # 必需：通用指南
Read references/executor-general.md       # 通用灵活样式
Read references/executor-consultant.md    # 咨询样式
Read references/executor-consultant-top.md # 顶级咨询样式（MBB 级别）
```

> 只需要阅读 executor-base + 一个样式文件。

**设计参数确认（强制）**：在生成第一个 SVG 之前，执行者必须审查并输出设计规范中的关键设计参数（画布尺寸、配色方案、字体计划、正文字号），以确保符合规范。详见 executor-base.md 第 2 节。

> ⚠️ **仅主智能体规则**：第 6 步的 SVG 生成必须保留在当前主智能体中，因为页面设计依赖于完整的上游上下文（源内容、设计规范、模板映射、图像决策和跨页一致性）。不要将任何幻灯片 SVG 生成委托给子智能体。
> ⚠️ **生成节奏规则**：确认全局设计参数后，执行者必须在一个连续的主智能体上下文中逐页顺序生成页面。不要将第 6 步分成每批 5 页的页面批次。

**视觉构建阶段**：
- 在一个连续过程中逐页顺序生成 SVG 页面 → `<项目路径>/svg_output/`

**逻辑构建阶段**：
- 生成演讲者备注 → `<项目路径>/notes/total.md`

**✅ 检查点 — 确认所有 SVG 和备注已完全生成。直接进入第 7 步后处理**：
```markdown
## ✅ 执行者阶段完成
- [x] 所有 SVG 已生成到 svg_output/
- [x] 演讲者备注已生成到 notes/total.md
```

---

### 第 7 步：后处理与导出

🚧 **门槛**：第 6 步完成；所有 SVG 已生成到 `svg_output/`；演讲者备注 `notes/total.md` 已生成。

> ⚠️ 以下三个子步骤必须**逐个单独执行**。每个命令必须在运行下一个之前完成并确认成功。
> ❌ **切勿**将三个命令放在一个代码块或单个 shell 调用中。

**第 7.1 步** — 拆分演讲者备注：
```bash
python3 ${SKILL_DIR}/scripts/total_md_split.py <项目路径>
```

**第 7.2 步** — SVG 后处理（图标嵌入 / 图像裁剪与嵌入 / 文本扁平化 / 圆角矩形转路径）：
```bash
python3 ${SKILL_DIR}/scripts/finalize_svg.py <项目路径>
```

**第 7.3 步** — 导出 PPTX（默认嵌入演讲者备注）：
```bash
python3 ${SKILL_DIR}/scripts/svg_to_pptx.py <项目路径> -s final
# 默认：生成两个文件 — 原生形状（.pptx）+ SVG 参考（_svg.pptx）
# 使用 --only native  跳过 SVG 参考版本
# 使用 --only legacy  仅生成 SVG 图像版本
```

> ❌ **切勿**使用 `cp` 替代 `finalize_svg.py` — 它执行多个关键处理步骤
> ❌ **切勿**直接从 `svg_output/` 导出 — 必须使用 `-s final` 从 `svg_final/` 导出
> ❌ **切勿**添加额外标志，如 `--only`

---

## 角色切换协议

切换角色之前，您**必须先阅读**相应的参考文件——禁止跳过。输出标记：

```markdown
## [角色切换：<角色名称>]
📖 阅读角色定义：references/<文件名>.md
📋 当前任务：<简要描述>
```

---

## 参考资源

| 资源 | 路径 |
|------|------|
| 共享技术约束 | `references/shared-standards.md` |
| 画布格式规范 | `references/canvas-formats.md` |
| 图像布局规范 | `references/image-layout-spec.md` |
| SVG 图像嵌入 | `references/svg-image-embedding.md` |

---

## 注意事项

- 不要向后处理命令添加额外标志，如 `--only`——按原样运行
- 本地预览：`python3 -m http.server -d <项目路径>/svg_final 8000`
