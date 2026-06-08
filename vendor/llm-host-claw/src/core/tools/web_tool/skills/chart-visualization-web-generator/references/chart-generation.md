# 图表生成场景

## 场景描述
为用户仅生成一张图表，如折线图、柱状图、饼图、mermaid图表等各种类型的数据可视化图表，不要生成英雄页等其他内容。

## 支持的图表类型
- 柱状图、折线图、饼图、散点图、面积图等Echarts图表类型
- mermaid流程图等图表类型

## 设计目标
- **视觉吸引力**：创造一个在视觉上令人印象深刻的图表，能够立即吸引用户的注意力，并激发他们的阅读兴趣。
- **可读性**：确保内容清晰易读，无论在桌面端还是移动端，都能提供舒适的阅读体验。

## 设计指导
1. 生成的图表必须有标题、图例等，均放在图表画布内部，标题居中，图例放在标题下方；
2. 坐标轴标题位置规范：
   - Y轴标题（如“产品名称”“温度(℃)”）：默认放置在Y轴最顶部（end），禁止居中（middle）导致与分类标签重叠；
   - X轴标题（如“时间”“日期”）：默认放置在X轴最右侧，禁止超出图表画布（绘图区域）的右边缘，与图表画布的右边缘保留至少10px间距；
3. 文字显示：所有文字（包括坐标轴标题、分类名、图例、数值标注）完整显示，无截断、无遮挡、无重叠，清晰可读。
4. 代码中使用 const 声明常量时，与常量中间必须加空格，保证图表正常显示出来。

## 技术规范
1. 使用 HTML5、Font Awesome、Tailwind CSS 、ECharts、mermaid和必要的 JavaScript。
   - ECharts使用`<script src="https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/echarts.js"></script>`
   - mermaid使用`https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js`
   - Font Awesome：`https://cdn.bootcdn.net/ajax/libs/font-awesome/6.4.0/css/all.min.css`
   - Tailwind CSS：`<link href="https://cdn.bootcdn.net/ajax/libs/tailwindcss/2.2.19/tailwind.min.css"; rel="stylesheet">`
   - 字体用 `<link rel="preconnect" href="https://fonts.proxy.ustclug.org">` + `font-display:swap`
   `<link rel="preconnect" href="fonts-gstatic.proxy.ustclug.org" crossorigin>`
   - font-family: ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"。
   - 除 Tailwind、FontAwesome、Echart.js、mermaid 官方 CDN 外，禁止任何第三方框架；自定义 JS 仅用原生 ES6，单文件 ≤ 400 行。
2. 不能使用自定义颜色名称（如primary/secondary），必须只使用Tailwind内置颜色：gray、indigo、purple、blue、green、yellow、red等。需要不同深浅的配色时，使用内置色阶，如：indigo-50、indigo-100...indigo-900。Tailwind标准色阶只有：50、100、200、300、400、500、600、700、800、900。
3. 实现完整的响应式，必须在所有设备上（手机、平板、桌面）完美展示。
4. 所有资源必须可本地离线打开，禁止任何「本地 dev 时才生效」的构建步骤。
5. 禁止使用 `<style type="text/tailwindcss">` 标签（包括在该标签内写 tailwind.config 配置）；所有 Tailwind 自定义配置（如 theme.extend）必须写在独立的 `<script>` 标签中（在 CDN 脚本之后）。


## 输出要求
- 以markdown格式，直接给出完整单文件 `.html` 源码，不省略任何技术细节，输出必须有```html ```。
- 所有代码必须安全，禁止以下内容：
  - 任何形式的 XSS 漏洞
  - eval()、new Function()、setTimeout(string) 等动态执行
  - innerHTML 拼接用户可控内容
  - 利用原型链执行代码（如 constructor.constructor）
  - 禁止输出任何恶意代码、安全漏洞或违反安全规范的内容。


## 生成流程

1. **理解需求**
   - 确定图表类型
   - 收集数据
   - 确定样式要求

2. **选择图表库**
   - 根据复杂度选择合适的库（ECharts或者mermaid）
   - 考虑性能和兼容性

3. **生成代码**
   - 创建HTML结构
   - 添加必要的CSS样式
   - 实现图表逻辑

4. **优化调整**
   - 响应式适配
   - 交互功能
   - 动画效果

## 最佳实践

- 使用响应式设计，确保在不同设备上正常显示
- 添加图例和标签，提高可读性
- 使用合适的颜色方案，考虑色盲用户
- 添加数据提示（tooltip），提供详细信息
- 优化性能，避免渲染过多数据点
