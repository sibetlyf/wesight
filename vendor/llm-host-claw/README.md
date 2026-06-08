# MOMA CLI 使用指南

## 概览

仓库当前已经提供一个可直接使用的本地 CLI，目标是尽量接近 Codex 的交互和消息流，同时保留本项目的 Subagent / Team 演进方向。

- CLI 模式：交互聊天、单次运行、slash commands、resume/history
- Headless 模式：结构化 JSON 输出、标准 SSE 流式输出
- Web 模式：`moma web` 同时拉起 backend 和 `swarm-ui`
- MCP 管理：单文件配置导入、CLI 管理、启动前自动探活
- 本地历史：自动保存原始事件 JSON，支持 `history` / `resume`
- Sandbox：已接入统一 `SandboxManager`，覆盖 shell、web、browser skill、vibe coding 等主要子进程入口

当前 CLI 主命令：

- `run`
- `chat`
- `sessions`
- `history`
- `resume`
- `doctor`
- `config`
- `mcp`
- `serve`
- `web`

## 开箱即用安装

目标是把这个仓库尽量做成“拉代码到本地后，一键初始化即可直接使用”的体验。

### Windows 一键初始化

仓库根目录执行：

```powershell
.\bootstrap-moma.ps1
```

如果你还要开发依赖：

```powershell
.\bootstrap-moma.ps1 -Dev
```

如果你还要本地浏览器自动化依赖：

```powershell
.\bootstrap-moma.ps1 -WithBrowsers
```

这个脚本会自动：

- 执行 Python 侧 `uv sync`
- 安装 `swarm-ui` 的 `npm` 依赖
- 可选安装 Playwright Chromium

初始化完成后可直接运行：

```powershell
.\start-moma.ps1
.\start-moma.ps1 web
```

### macOS / Linux 一键初始化

仓库根目录执行：

```bash
chmod +x bootstrap-moma.sh
./bootstrap-moma.sh
```

可选：

```bash
./bootstrap-moma.sh --dev
./bootstrap-moma.sh --with-browsers
```

初始化完成后可直接运行：

```bash
uv run python -m moma_cli --config config.json chat
uv run python -m moma_cli --config config.json web
```

### 通用 CLI 初始化

如果你已经能运行 Python 入口，也可以直接：

```bash
uv run python -m moma_cli init
uv run python -m moma_cli init --dev
uv run python -m moma_cli init --with-browsers
```

或安装脚本入口后：

```bash
moma init
```

`moma init` 会自动：

- 安装 Python 依赖
- 安装 `swarm-ui` 前端依赖
- 可选安装浏览器运行时

### 最短上手路径

如果你只是想把仓库拉到本地然后直接跑：

Windows：

```powershell
git clone <repo>
cd llm-host-claw
.\bootstrap-moma.ps1
.\start-moma.ps1
```

macOS / Linux：

```bash
git clone <repo>
cd llm-host-claw
chmod +x bootstrap-moma.sh
./bootstrap-moma.sh
uv run python -m moma_cli --config config.json chat
```

### 1. 安装依赖

```bash
uv sync --extra dev
```

### 2. 使用单文件配置

推荐使用单文件 `config.json`。同一个文件可以同时承载：

- 模型配置
- toolkits
- `mcpServers`

你可以先检查配置是否可被 CLI 正确识别：

```bash
moma config --path config.json
```

查看当前 CLI 环境摘要：

```bash
moma --config config.json doctor
moma --config config.json doctor --fix
```

`doctor` 现在不只是查看状态，也支持自动修复本地依赖链路。

示例：

```bash
moma doctor --fix
moma doctor --fix --dev
moma doctor --fix --with-browsers
moma doctor --fix --target python
moma doctor --fix --target web
moma doctor --fix --target browsers
```

`doctor --fix` 当前会自动尝试：

- 执行 `uv sync`
- 安装 `swarm-ui` 的 `npm` 依赖
- 可选安装 Playwright Chromium

`doctor` 当前会输出分项检查结果，包括：

- `python_toolchain`
- `web_toolchain`
- `swarm_ui_dir`
- `swarm_ui_dependencies`
- `playwright_chromium`

### 3. 启动 CLI

Windows 下如果你不想每次手动设置 `PYTHONPATH` 和输入完整模块路径，可以直接使用仓库根目录的启动脚本：

```powershell
.\start-moma.ps1
```

默认行为：

- 自动使用 `config.json` 作为 `--config`
- 自动设置 `PYTHONPATH=src`
- 默认进入 `chat` 交互模式

如果不用 PowerShell 启动脚本，也可以直接：

```bash
uv run python -m moma_cli chat --config config.json
```

或安装脚本入口后直接：

```bash
moma --config config.json chat
```

你也可以把其他参数原样传给 CLI：

```powershell
.\start-moma.ps1 doctor
.\start-moma.ps1 run "你是谁，请用一句话回答。"
.\start-moma.ps1 config --path config.json
```

单次运行：

```bash
moma --config config.json run "你是谁，请用一句话回答。"
```

交互模式：

```bash
moma --config config.json chat
```

带首条 prompt 进入交互：

```bash
moma --config config.json chat --prompt "先告诉我你看到了哪些文件"
```

JSON 流式事件模式：

```bash
moma --config config.json --json run "hello"
```

> 说明：`--json` 模式下输出的是标准 JSON 事件流；普通 CLI 模式只展示消息、工具调用、工具结果和必要系统信息，不直接展示原始 JSON。

### 4. 全局参数

这些参数可以放在主命令前：

- `--config <path>`：主配置文件
- `--workspace <dir>`：CLI userspace 根目录，默认是当前目录下的 `.moma_cli`
- `--session-id <id>`：复用指定会话
- `--user-id <id>`：覆盖 `USER_ID`
- `--api-key <key>`：覆盖 `API_KEY`
- `--authorization <token>`：覆盖 `AUTHORIZATION`
- `--mcp-config <path>`：额外导入一份 MCP 配置到当前 workspace
- `--sandbox`：开启 sandbox
- `--sandbox-root <dir>`：指定 sandbox 根目录，默认是当前 session 的 workspace
- `--json`：输出原始标准事件 JSON
- `--headless`：关闭 UI，输出结构化结果
- `--stream`：仅对 `--headless` 有意义，输出标准 SSE

### 5. Headless / API 模式

```bash
moma --config config.json --headless run "hello"
moma --config config.json --headless --stream run "hello"
```

`--headless` 会关闭所有终端 UI，直接输出结构化 JSON，适合被其他程序当作 API 调用入口使用。

如果再加 `--stream`，输出会变成**标准 SSE**：每条事件使用 `event:` + `data:` 编码，最后补一条 `response.summary` 汇总事件，适合流式消费。

约束：

- `--headless` 不能和 `--json` 同时使用
- `headless chat` 必须配合 `--prompt`，不支持交互式 stdin 循环

Headless 流式输出示例：

```text
event: response.created
data: {"type":"response.created","response_id":"...","session_id":"...","run_id":"...","sequence":0,"timestamp":"...","agent":{"id":"...","name":"Orchestrator","kind":"orchestrator","mode":"subagent"},"data":{"status":"created"}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","response_id":"...","session_id":"...","run_id":"...","sequence":1,"timestamp":"...","agent":{"id":"...","name":"Orchestrator","kind":"orchestrator","mode":"subagent"},"data":{"item_id":"item_msg_1","delta":"Hello"}}

event: response.summary
data: {"mode":"headless","prompt":"hello","exit_code":0,"message_count":2,"tool_count":0,"subagent_count":0,"events":[...]}
```

Headless 输出结构示例：

```json
{
  "mode": "headless",
  "prompt": "hello",
  "exit_code": 0,
  "message_count": 3,
  "tool_count": 1,
  "subagent_count": 1,
  "events": [
    {
      "type": "response.created",
      "response_id": "...",
      "session_id": "...",
      "run_id": "...",
      "sequence": 0,
      "timestamp": "...",
      "agent": { "id": "...", "name": "...", "kind": "orchestrator", "mode": "subagent" },
      "data": { "status": "created" }
    }
  ]
}
```

### 6. 本地历史与恢复

每次 `run`、`chat`、`--headless run`、`--headless --stream run` 完成后，CLI 会自动把原始 `response.*` 事件保存到本地 history JSON。

查看会话：

```bash
moma --config config.json sessions
```

查看历史记录：

```bash
moma --config config.json history
moma --config config.json history list
moma --config config.json history show <entry-id>
```

恢复对话：

```bash
moma --config config.json resume
moma --config config.json resume <session-id>
```

交互模式里也支持：

```text
/history
/history show <entry-id>
/resume
/resume <session-id>
/resume 1
```

恢复语义说明：

- `resume` 恢复的是指定 `session_id` 最近一次保存的历史事件
- 交互模式下 `/resume` 会列出会话供选择
- 非交互模式下可直接传 `--session-id <id>` 继续在同一会话下运行

### 7. Web 模式

启动方式：

```bash
moma --config config.json web
moma --config config.json web --host 0.0.0.0 --port 3018
```

首次使用前端前，先安装 `swarm-ui` 依赖：

```bash
cd swarm-ui
npm install
```

现在 `moma web` 默认会在检测到缺少 `swarm-ui/node_modules/next` 时自动执行一次 `npm install`，所以首次启动通常不需要手动安装。

如果你不想让 CLI 自动安装依赖，可以显式关闭：

```bash
moma --config config.json web --no-install
```

`--no-install` 下如果依赖缺失，就会报错退出。本质上仍然是 `swarm-ui/node_modules` 里没有安装 `next`。

当前 `moma web` 会启动两个进程：

- backend：默认监听 `http://<host>:<port+1>`
- frontend：`swarm-ui` dev server，默认入口 `http://<host>:<port>/moma`

终端会打印：

- `MOMA Web available at ...`
- `MOMA Backend available at ...`

说明：当前实现仍是开发模式双进程启动，不是最终的 `moma serve` 常驻生产部署模式。

### 8. Serve 模式

如果你只想启动 backend API，不启动前端：

```bash
moma --config config.json serve
moma --config config.json serve --host 0.0.0.0 --port 3019
```

启动后会监听：

- `GET /health`
- `POST /api/orchestrator/run`
- `GET /api/web/sessions`
- `GET /api/web/history/latest?session_id=...`

这是当前最适合作为“持续监听服务”的模式；`web` 更适合本地联调 UI。

### 9. MCP 配置与探活

单文件配置支持直接内嵌 MCP：

```json
{
  "model": {
    "id": "gpt-5.4",
    "provider": "openai",
    "base_url": "https://www.cctq.ai/v1",
    "api_key": "YOUR_API_KEY"
  },
  "toolkits": [],
  "mcpServers": {
    "bing-cn-mcp-server": {
      "type": "sse",
      "url": "https://example.com/sse"
    }
  }
}
```

当前 CLI 同时兼容：

- `transport: "sse"`
- `type: "sse"`

因此可以直接导入常见 MCP 配置片段，不需要手工改字段名。

常用命令：

```bash
moma --config config.json mcp list
moma --config config.json mcp check
moma --config config.json mcp add --name exa --url https://example.com/sse
moma --config config.json mcp remove --name exa
moma --config config.json mcp import --path extra-mcp.json
```

`run` / `chat` 启动前，CLI 会自动探活当前 session 可见的 MCP server，并在 CLI 中打印状态摘要。

### 10. `mcp` 子命令的作用域规则

这是最容易踩坑的一点：

- `moma --workspace <dir> mcp add/list/check/remove ...`
  - 操作的是**基础 workspace** 下的 `tools/`
- `moma --config config.json --workspace <dir> --session-id <sid> mcp list`
  - 操作的是该 **session 对应 WORKSPACE** 下的 `tools/`
  - 会包含当前单文件配置导入到该会话的内嵌 MCP

示例：

```bash
# 在基础 workspace 下直接管理 MCP
moma --workspace .moma_cli mcp add --name exa --url https://example.com/sse
moma --workspace .moma_cli mcp list

# 查看某个会话通过单文件配置导入后的 MCP
moma --config config.json --workspace .moma_cli --session-id session-1 mcp list
```

### 11. 常用 slash commands

交互模式下可直接输入：

- `/help`
- `/exit`
- `/quit`
- `/clear`
- `/session`
- `/workspace`
- `/runspace`
- `/mcp list`
- `/mcp check`
- `/mcp add ...`
- `/mcp remove ...`
- `/mcp import ...`

交互模式支持 slash 联想：

- 输入 `/` 会列出全部指令
- 输入 `/res...` 会联想 `/resume ...`
- `/resume` 会动态列出最近历史会话

### 12. Sandbox

开启方式：

```bash
moma --config config.json --sandbox chat
moma --config config.json --sandbox --sandbox-root G:\\safe-workspace run "列出目录"
```

当前 sandbox 行为：

- 默认把根目录限制在当前 session 的 `WORKSPACE`
- 限制 shell 命令中的 `../` / `..\\` 逃逸
- 限制显式绝对路径越界
- 限制 `cwd` 越界
- 统一接管主要子进程入口：shell、`moma web`、browser local skill、vibe coding

当前平台策略：

- Linux：优先 `bwrap`，缺失时回退为逻辑沙箱
- macOS：优先 `sandbox-exec`，缺失时回退为逻辑沙箱
- Windows：当前还是逻辑沙箱回退模式，还没有完成 Restricted Token / ACL 级别隔离

这意味着：

- 当前已经能稳定限制大部分 CLI 和工具链的文件访问边界
- 但 Windows 还不是完整系统级隔离
- 网络隔离和 syscall 级限制也还未完成

## Headless API 文档

### 命令

```bash
moma --config <path> --headless run "<prompt>"
moma --config <path> --headless --stream run "<prompt>"
moma --config <path> --headless chat --prompt "<prompt>"
```

### 参数

- `--headless`：关闭所有 UI，输出结构化 JSON
- `--stream`：仅在 `--headless` 下有意义，输出标准 SSE
- `--json`：保留原始 `response.*` 事件流（不能与 `--headless` 同时使用）
- `run <prompt...>`：单次执行
- `chat --prompt <text>`：headless 下等价于单次执行

### 输出字段

- `mode`：固定为 `headless`
- `prompt`：原始输入
- `exit_code`：进程退出码
- `message_count`：消息相关事件数量
- `tool_count`：工具事件数量
- `subagent_count`：子智能体事件数量
- `events`：完整 `response.*` 事件数组（每项均为标准事件 JSON）

### Headless 流式输出

当使用 `--headless --stream` 时，stdout 不再输出单个聚合 JSON，而是输出标准 SSE 事件流：

- `event: response.*` + `data: {...}`：单条标准 `response.*` 事件
- `event: response.summary` + `data: {...}`：最终汇总对象

这适合：

- 服务端直接透传或转发 SSE
- CLI 被其他进程通过管道消费
- 需要实时事件 + 最终总结同时保留的场景

### 事件格式

`events[]` 与 `--json` 模式下的单条事件一致，字段包括：

- `type`
- `event_id`
- `response_id`
- `session_id`
- `run_id`
- `sequence`
- `timestamp`
- `agent`
- `data`

### 适用场景

- 作为脚本/服务的 API 调用层
- 采集标准事件并自行二次处理
- 嵌入到自动化流程、CI、工作流引擎中

## 依赖环节

### 核心依赖

#### 1. Node.js 环境 (LTS 版本)

- **用途**：运行 VibeCoding CLI 工具
- **安装方式**：
  - Windows：从 [Node.js 官网](https://nodejs.org/) 下载并安装
  - macOS：`brew install node`
  - Ubuntu/Debian：
    ```bash
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
    sudo apt-get install -y nodejs
    ```

#### 2. Python 环境 (>=3.12)

- **用途**：运行项目核心代码
- **安装方式**：建议使用 uv进行管理
- **依赖管理**：使用 uv 管理依赖
  - 安装重要依赖：`uv sync`
  - 安装开发依赖：`uv sync --extra dev`

### opencode 依赖

#### ccr (Claude Code Router)

- **用途**：代码路由工具
- **安装命令**：
  ```bash
  npm install -g @anthropic-ai/claude-code @musistudio/claude-code-router
  npm cache clean --force
  ```

#### opencode

- **用途**：AI 编码工具
- **安装命令**：
  ```bash
  npm i -g opencode-ai
  ```

#### Bun

- **用途**：JavaScript 运行时，用于安装 oh-my-opencode
- **安装命令**：
  ```bash
  curl -fsSL https://bun.sh/install | bash
  ```

#### oh-my-opencode (可选)

- **用途**：opencode 插件
- **安装命令**：
  ```bash
  bunx oh-my-openagent install --no-tui --claude=no --gemini=no --copilot=no
  ```

### Browser Agent 依赖

本项目内置一个基于 **browser-use** 的 Browser Agent，用于执行网页访问、点击、输入、页面提取和多轮网页任务。

#### 1. 安装 browser-use

- **用途**：浏览器自动化工具
- **安装命令**：
  ```bash
  uv add browser-use
  uv sync
  ```

#### 2. 安装浏览器运行时

- **用途**：提供浏览器环境
- **安装命令**：

  ```bash
  # 推荐方式
  uvx browser-use install

  # 或使用 Playwright 安装 Chromium
  uvx playwright install chromium

  # Linux 服务器上更稳妥的方式
  uvx playwright install chromium --with-deps
  ```

## 前序步骤

### 1. Workspace 初始化

- 将额外的子智能体、工具(mcp)和 skills 等全部存入 workspace 中（可选），挂载到/workspace，并将路径 workspace 路径写到 env 中的 WORKSPACE 中
- 若用户上传了文件，将文件映射至 workspace/runs/ 目录下
- 在workspace目录创建.claude文件夹
- 将src/configs/claude下的全部文件复制到.claude文件夹

### 2. 环境变量初始化

- 将 /.../<userspace> 路径写到 env 中的 USERSPACE 中
- 将 /.../<userspace>/sessions/ 路径写到 env 中的 SESSIONSPACE 中
- 将 /.../<userspace>/sessions/<session_id>/ 路径写到 env 中的 WORKSPACE 中
- 将 /.../<userspace>/sessions/<session_id>/runs/ 路径写到 env 中的 RUNSPACE 中
- 将 `{"user_id", "record_id", "authorization","api_key"}` 分别存入 env 中的 USER_ID, RECORD_ID, AUTHORIZATION, API_KEY中
- 将 OrchestratorConfig 序列化后存入 env 中的 ORCHESTRATOR_CONFIG 中

### 3. opencode 配置

- 在环境变量中加入JIUTIAN_BASE_URL
- 修改~/.config/opencode下的opencode.json与oh-my-opencode.json

参考格式:

**opencode.json**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": [
    "oh-my-openagent@latest"
  ],
  "provider": {
    "MOMA": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "JIUTIAN MOMA",
      "options": {
        "baseURL": "YOUR API URL",
        "apiKey": "YOUR API KEY"
      },
      "models": {
        "qwen3.5-397B-fp8": {
          "name": "qwen3.5"
        }
  },
  "model": "MOMA/qwen3.5-397B-fp8"
}
```

**oh-my-opencode.json**

```json
{
  "$schema": "https://raw.githubusercontent.com/code-yeongyu/oh-my-openagent/dev/assets/oh-my-opencode.schema.json",
  "agents": {
    "hephaestus": {
      "model": "MOMA/qwen3.5-397B-fp8"
    },
    "oracle": {
      "model": "MOMA/kimi-k2-5-thinking"
    },
    "librarian": {
      "model": "MOMA/qwen3.5-397B-fp8"
    },
    "explore": {
      "model": "MOMA/qwen3.5-397B-fp8"
    },
    "atlas": {
      "model": "MOMA/kimi-k2-5-thinking"
    },
    "sisyphus-junior": {
      "model": "MOMA/qwen3.5-397B-fp8"
    }
  }
}
```

### 4. Browser Agent 配置（可选）

如果使用 Browser Agent，需要进行以下配置：

#### 环境变量

- `JIUTIAN_BROWSER_MODEL`：browser-use 内层执行模型
- `JIUTIAN_API_KEY`：browser agent 调用模型时使用的 key
- `BROWSER_USE_DISABLE_SERVER_MEMORY`：可选，用于清理输入中携带的 previous interaction summary，减少旧会话摘要对当前 browser task 的干扰，最好设置为 1
- `BROWSER_USE_DISABLE_EXTENSIONS`：可选，运行环境如果访问 github 等网站不稳定最好设置为 1，不然拉起浏览器之前会先下载扩展，容易卡住

#### 运行目录与浏览器 Profile

Browser Agent 默认是**按 session 复用浏览器**的，并且会为每个 session 准备独立的浏览器数据目录，用来保存 cookie、localStorage 和登录态。当前实现的优先级如下：

1. 若显式配置 `user_data_dir`，则优先使用它
2. 否则若环境变量 `BROWSER_TOOLKIT_SESSION_DIR` 存在，则使用该目录
3. 否则默认落到 `WORKSPACE/.browser_toolkit_sessions/<session_id>`

这意味着在多轮任务中，同一个 `session_id` 会天然复用同一份浏览器 profile；而不同 session 默认彼此隔离。

# Router 模式与子智能体分发

Orchestrator 支持两种分发子任务的方式，通过子智能体配置或调用参数进行控制：

### 1. Router 模式 (`mode: "router"`)
- **核心思想**：高性能直连。
- **运行逻辑**：如果子智能体定义了 `entrypoint`（入口函数），Orchestrator 会直接调用该 Python 函数，绕过完整的 Agent 实例化和模型推理过程。
- **适用场景**：逻辑明确、对响应速度要求极高的原子化任务（例如：编程分发、天气查询）。

### 2. Subagent 模式 (`mode: "subagent"`)
- **核心思想**：标准 Agent 协作。
- **运行逻辑**：Orchestrator 会忽略 `entrypoint`，创建一个完整的 `Agent` 实例，加载其专属的工具、技能和指令，进行多轮思考与对话。
- **适用场景**：需要复杂规划、多工具协作或开放式对话的任务。

# Agent 配置文件规范 (`agent.md`)

每个子智能体由一个 Markdown 文件定义（通常存放在 `src/core/agents/` 目录下）。文件包含 YAML 格式的元数据头部和任务指令。

### 1. 头部配置项说明

- **`mode`**: 默认路由模式。设置为 `router` 时优先尝试入口函数。
- **`entrypoint`**: 字符串，指向具体 Python 函数的完整路径（格式：`包名.模块名.类名.方法名` 或 `包名.模块名.函数名`）。
- **`entrypoint_params`**: **[重要]** 当使用 `router` 模式时，必须在此处列出入口函数所需的参数及其描述。Orchestrator 将据此动态解析用户意图并自动注入参数。

### 2. 配置示例 (`vibe_coding.md`)

```markdown
---
mode: router
entrypoint: core.tools.vibe_tool.vibe_toolkit.VibeCodingToolkit.coding_assign_task
entrypoint_params:
  task_name: 任务名称，用于唯一标识该编程任务（如：hello_world_task）
  prompt: 完整的编程任务描述，包括功能需求和技术细节
---

# 智能体指令
你是一个资深的编程专家，负责接收分发并执行具体的编码任务...
```

### 3. 参数自动注入规则
- Orchestrator 启动时会扫描所有 `agent.md` 文件。
- 如果检测到 `entrypoint_params`，它会将参数描述合并到路由工具的提示词中。
- 在 `router` 模式执行时，系统会自动从上下文提取对应的参数值传递给函数。
- 默认支持 `run_context`、`envar`、`subagent_name` 等系统级参数的自动注入。

# Workspace 规范

这是一个沙箱内工作空间目录，用于存储 Agent 运行过程中产生的各类数据和制品。

## 用途

此目录主要用于存储 Agent 运行过程中产生的对话属性、中间调用结果、自定义技能、子智能体和待办清单等数据。

## 目录结构

```text
userspace/        # 用户空间目录                                      # export USERSPACE=/userspace
├── .agno.db      # agno 数据库文件，存储**记忆**，**对话**和**总结**
├── skills/       # 全局用户自定义的技能目录
└── sessions/     # 对话空间目录                                      # export SESSIONSPACE=/userspace/sessions/
    ├── session-1     # 单个对话空间                                  # export WORKSPACE=/userspace/session-1
    │   ├── runs/         # 用户上传文件所在地，中间调用产生的结果和制品   # export RUNSPACE=/userspace/session-1/runs
    │   ├── skills/       # 用户自定义的技能
    │   ├── tools/        # 用户自定义或者外层传入的mcp工具卡片
    │   ├── subagents/    # 协调器创建的子智能体存储或者外部的子智能体
    │   └── todo/         # 对话中产生的待办清单
    └── session-2 ...
```

## 目录环境变量注意事项

- 和文件有交互的工具，应当默认在`RUNSPACE`目录下执行并写入文件
- shell 工具权限锁定在`SESSIONSPACE`目录下，不能超出此目录，终端初始化录应该是`RUNSPACE`目录
- `USERSPACE` 理论上用于`Orchestrator`在初始化的时候加载`db`，加载 `skills`
- `WORKSPACE`理论上只用于 `todo`、`subagent`工具集关联目录, 及`skills`和`tools`的加载

## 目录说明

### `.agno.db`

用于存储 Agent 运行过程中产生的对话内容

### `runs/`

用于存储中间调用产生的结果和制品。

- 存放 Agent 运行过程中的中间结果
- 保存调用产生的临时文件和制品
- 用于调试和追踪执行过程

### `skills/`

用于存储用户自定义的技能。

- 用户可以在此目录添加自定义技能代码
- 支持技能的动态加载和执行
- 便于扩展 Agent 的能力

### `tools/`

用于存储用户自定义或者外层传入的mcp工具卡片。

- 用户可以在此目录添加自定义工具卡片
- 支持工具卡片的动态加载和执行
- 便于扩展 Agent 的能力

### `subagents/`

用于存储智能体创建的子智能体。

- 保存 Orchestrator 创建的子智能体配置和状态
- 支持多智能体协作的场景
- 管理子智能体的生命周期

### `todo/`

用于保存所有对话中产生的待办清单。

- 存储对话过程中生成的任务列表
- 支持任务的创建、更新和完成状态管理
- 便于追踪和管理对话中的待办事项

## 注意事项

- 此目录下的文件通常由程序自动生成和管理
- 在版本控制中可能需要忽略部分运行时生成的临时文件

# skill规范

1. scripts 拼写问题
2. references 扫描所有子目录 md 文件，不想被扫到前面加个.
3. scripts 只扫描目录下的文件
4. md 不能让模型用 python 去执行，而是用get_skill_script
