# MOMA API 详细使用说明

本文档基于当前仓库实现整理，覆盖：

- `moma serve` 暴露的 HTTP API
- `moma web` 使用到的 Web API
- `moma --headless` / `--stream` 的结构化输出协议
- 标准 `response.*` 消息体结构
- 本地 history / session 相关返回结构

如果代码与本文档冲突，以实现为准。本文档对应的核心实现位于：

- `src/moma_cli/web.py`
- `src/api/routes/orchestrator.py`
- `src/moma_cli/commands.py`
- `src/protocol/response_events.py`
- `src/protocol/normalizer.py`
- `src/moma_cli/history.py`

---

## 1. 总览

项目当前对外有两类 API 面：

### 1.1 HTTP 服务 API

通过以下命令启动：

```bash
moma --config config.json serve
```

默认监听：

- `http://127.0.0.1:3019`

主要接口：

- `GET /health`
- `POST /api/orchestrator/run`
- `GET /api/orchestrator/status`
- `GET /api/web/sessions`
- `GET /api/web/history/latest?session_id=...`

### 1.2 CLI Headless API

通过命令行直接输出 JSON 或 SSE：

```bash
moma --config config.json --headless run "hello"
moma --config config.json --headless --stream run "hello"
```

这类模式不启动 HTTP 服务，但其输出本身就是一种稳定的 API 协议。

---

## 2. 启动方式

## 2.1 启动后端服务

```bash
moma --config config.json serve
```

指定地址：

```bash
moma --config config.json serve --host 0.0.0.0 --port 3019
```

启动成功后，终端会输出：

```text
MOMA Serve available at http://127.0.0.1:3019
```

## 2.2 启动 Web 模式

```bash
moma --config config.json web
```

默认会启动两个进程：

- 前端：`http://127.0.0.1:3018/moma`
- 后端：`http://127.0.0.1:3019`

可自定义：

```bash
moma --config config.json web --host 127.0.0.1 --port 3018
```

注意：

- `web` 本质上复用同一套 backend API
- `web` 会自动设置 `NEXT_PUBLIC_BACKEND_ORIGIN`
- 如果 `swarm-ui` 缺依赖，默认自动 `npm install`

## 2.3 启动 Headless 单次 JSON 输出

```bash
moma --config config.json --headless run "你好"
```

## 2.4 启动 Headless SSE 输出

```bash
moma --config config.json --headless --stream run "你好"
```

## 2.5 Headless Chat 单次调用

```bash
moma --config config.json --headless chat --prompt "你好"
```

说明：

- `--headless chat` 必须带 `--prompt`
- 不支持交互式 stdin 聊天循环

---

## 3. HTTP API 详细说明

## 3.1 `GET /health`

### 作用

检查服务存活，并返回当前运行上下文。

### 请求示例

```bash
curl http://127.0.0.1:3019/health
```

### 返回示例

```json
{
  "status": "healthy",
  "userspace": "G:\\MOMA\\moma_cli\\llm-host-claw\\.moma_cli",
  "workspace": "G:\\MOMA\\moma_cli\\llm-host-claw\\.moma_cli\\sessions\\session-1",
  "session_id": "session-1"
}
```

### 字段说明

- `status`: 固定为 `healthy`
- `userspace`: 当前 userspace 路径
- `workspace`: 当前 session workspace 路径
- `session_id`: 当前环境中的 session id

---

## 3.2 `GET /api/orchestrator/status`

### 作用

返回 orchestrator 是否可接收请求。

### 请求示例

```bash
curl http://127.0.0.1:3019/api/orchestrator/status
```

### 返回示例

```json
{
  "status": "running",
  "message": "Orchestrator is ready to process requests"
}
```

---

## 3.3 `POST /api/orchestrator/run`

### 作用

以 HTTP SSE 的方式运行一次 orchestrator。

### Content-Type

```text
application/json
```

### 请求体模型

对应 `src/api/models/orchestrator.py` 中的 `OrchestratorRunRequest`：

```json
{
  "message": "string, 必填",
  "session_id": "string, 可选",
  "userspace": "string, 可选",
  "extra": {
    "location": "string, 可选",
    "media": [
      {
        "url": "string, 必填",
        "mime_type": "string, 可选"
      }
    ]
  }
}
```

### `extra` 说明

`extra` 来源于 `src/protocol/extra_info.py`：

- `current_time` 由服务端自动生成
- `location` 可选
- `media` 可选，为媒体列表

### 最小请求示例

```bash
curl -N -X POST http://127.0.0.1:3019/api/orchestrator/run ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"你是谁\"}"
```

### 带 session 的请求示例

```json
{
  "message": "继续上一次对话，总结当前任务",
  "session_id": "session-demo-001",
  "userspace": "G:\\MOMA\\moma_cli\\llm-host-claw\\.moma_cli"
}
```

### 带 extra 的请求示例

```json
{
  "message": "请分析我上传的图片",
  "session_id": "session-media-001",
  "userspace": "G:\\MOMA\\moma_cli\\llm-host-claw\\.moma_cli",
  "extra": {
    "location": "Beijing",
    "media": [
      {
        "url": "G:\\MOMA\\moma_cli\\llm-host-claw\\runs\\diagram.png",
        "mime_type": "image/png"
      }
    ]
  }
}
```

### 返回类型

```text
text/event-stream
```

服务端会逐条输出：

```text
event: <response.type>
data: <json>

event: <response.type>
data: <json>
```

### SSE 返回示例

```text
event: response.created
data: {"type":"response.created","event_id":"evt_001","response_id":"resp_001","session_id":"session-demo-001","run_id":"run_root_001","sequence":0,"timestamp":"2026-06-05T09:00:00+00:00","agent":{"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},"data":{"status":"created","model":"gpt-5.4","provider":"openai"}}

event: response.in_progress
data: {"type":"response.in_progress","event_id":"evt_002","response_id":"resp_001","session_id":"session-demo-001","run_id":"run_root_001","sequence":1,"timestamp":"2026-06-05T09:00:00+00:00","agent":{"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},"data":{"status":"in_progress"}}

event: response.output_item.added
data: {"type":"response.output_item.added","event_id":"evt_003","response_id":"resp_001","session_id":"session-demo-001","run_id":"run_root_001","sequence":2,"timestamp":"2026-06-05T09:00:00+00:00","agent":{"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},"data":{"output_index":0,"item":{"id":"item_msg_orchestrator_run_root_001","type":"message","role":"assistant","status":"in_progress"}}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","event_id":"evt_004","response_id":"resp_001","session_id":"session-demo-001","run_id":"run_root_001","sequence":3,"timestamp":"2026-06-05T09:00:00+00:00","agent":{"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},"data":{"item_id":"item_msg_orchestrator_run_root_001","output_index":0,"content_index":0,"delta":"你好，我是 MOMA。"}}

event: response.output_text.done
data: {"type":"response.output_text.done","event_id":"evt_005","response_id":"resp_001","session_id":"session-demo-001","run_id":"run_root_001","sequence":4,"timestamp":"2026-06-05T09:00:01+00:00","agent":{"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},"data":{"item_id":"item_msg_orchestrator_run_root_001","output_index":0,"content_index":0,"text":""}}

event: response.completed
data: {"type":"response.completed","event_id":"evt_006","response_id":"resp_001","session_id":"session-demo-001","run_id":"run_root_001","sequence":5,"timestamp":"2026-06-05T09:00:01+00:00","agent":{"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},"data":{"status":"completed","usage":{}}}
```

### 错误返回

该路由捕获异常后返回：

```json
{
  "detail": "<error message>"
}
```

例如：

```json
{
  "detail": "Config file not found"
}
```

HTTP 状态码：`500`

---

## 3.4 `GET /api/web/sessions`

### 作用

列出本地 history 中最近的 session。

### 请求示例

```bash
curl http://127.0.0.1:3019/api/web/sessions
```

### 返回示例

```json
{
  "sessions": [
    {
      "entry_id": "hist_20260605T090000Z_ab12cd34",
      "created_at": "2026-06-05T09:00:00+00:00",
      "session_id": "session-a",
      "workspace": "G:\\MOMA\\moma_cli\\llm-host-claw\\.moma_cli\\sessions\\session-a",
      "mode": "chat",
      "prompt": "old prompt",
      "assistant_text_preview": "hello again",
      "path": "G:\\MOMA\\moma_cli\\llm-host-claw\\.moma_cli\\sessions\\session-a\\history\\hist_20260605T090000Z_ab12cd34.json"
    }
  ]
}
```

---

## 3.5 `GET /api/web/history/latest?session_id=...`

### 作用

返回某个 session 最新一次保存的原始事件记录。

### 请求示例

```bash
curl "http://127.0.0.1:3019/api/web/history/latest?session_id=session-a"
```

### 返回示例

```json
{
  "session_id": "session-a",
  "events": [
    {
      "type": "response.created",
      "event_id": "evt_001",
      "response_id": "resp_001",
      "session_id": "session-a",
      "run_id": "run_root_001",
      "sequence": 0,
      "timestamp": "2026-06-05T09:00:00+00:00",
      "agent": {
        "id": "orchestrator",
        "name": "Orchestrator",
        "kind": "orchestrator",
        "mode": "subagent",
        "parent_agent_id": null,
        "spawned_by_call_id": null,
        "team_id": null,
        "role": "lead"
      },
      "data": {
        "status": "created"
      }
    }
  ],
  "prompt": "old prompt"
}
```

---

## 4. CLI Headless API

## 4.1 非流式 JSON 输出

### 命令

```bash
moma --config config.json --headless run "hello"
```

### 返回结构

对应 `HeadlessRunResult`：

```json
{
  "mode": "headless",
  "prompt": "hello",
  "exit_code": 0,
  "message_count": 2,
  "tool_count": 1,
  "subagent_count": 1,
  "events": []
}
```

### 完整示例

```json
{
  "mode": "headless",
  "prompt": "hello",
  "exit_code": 0,
  "message_count": 2,
  "tool_count": 1,
  "subagent_count": 1,
  "events": [
    {
      "type": "response.created",
      "event_id": "evt_created",
      "response_id": "resp_demo",
      "session_id": "session-headless",
      "run_id": "run_root_001",
      "sequence": 0,
      "timestamp": "2026-06-05T09:00:00+00:00",
      "agent": {
        "id": "orchestrator",
        "name": "Orchestrator",
        "kind": "orchestrator",
        "mode": "subagent",
        "parent_agent_id": null,
        "spawned_by_call_id": null,
        "team_id": null,
        "role": "lead"
      },
      "data": {
        "status": "created"
      }
    },
    {
      "type": "response.output_text.delta",
      "event_id": "evt_delta",
      "response_id": "resp_demo",
      "session_id": "session-headless",
      "run_id": "run_root_001",
      "sequence": 1,
      "timestamp": "2026-06-05T09:00:00+00:00",
      "agent": {
        "id": "orchestrator",
        "name": "Orchestrator",
        "kind": "orchestrator",
        "mode": "subagent",
        "parent_agent_id": null,
        "spawned_by_call_id": null,
        "team_id": null,
        "role": "lead"
      },
      "data": {
        "item_id": "item_msg_1",
        "output_index": 0,
        "content_index": 0,
        "delta": "Hello"
      }
    },
    {
      "type": "response.tool_call.started",
      "event_id": "evt_tool",
      "response_id": "resp_demo",
      "session_id": "session-headless",
      "run_id": "run_root_001",
      "sequence": 2,
      "timestamp": "2026-06-05T09:00:00+00:00",
      "agent": {
        "id": "orchestrator",
        "name": "Orchestrator",
        "kind": "orchestrator",
        "mode": "subagent",
        "parent_agent_id": null,
        "spawned_by_call_id": null,
        "team_id": null,
        "role": "lead"
      },
      "data": {
        "name": "shell"
      }
    },
    {
      "type": "response.subagent.started",
      "event_id": "evt_sub",
      "response_id": "resp_demo",
      "session_id": "session-headless",
      "run_id": "run_root_001",
      "sequence": 3,
      "timestamp": "2026-06-05T09:00:00+00:00",
      "agent": {
        "id": "writer-agent",
        "name": "writer",
        "kind": "subagent",
        "mode": "subagent",
        "parent_agent_id": "orchestrator",
        "spawned_by_call_id": "call_001",
        "team_id": null,
        "role": "writer"
      },
      "data": {
        "subagent_name": "writer"
      }
    },
    {
      "type": "response.completed",
      "event_id": "evt_done",
      "response_id": "resp_demo",
      "session_id": "session-headless",
      "run_id": "run_root_001",
      "sequence": 4,
      "timestamp": "2026-06-05T09:00:01+00:00",
      "agent": {
        "id": "orchestrator",
        "name": "Orchestrator",
        "kind": "orchestrator",
        "mode": "subagent",
        "parent_agent_id": null,
        "spawned_by_call_id": null,
        "team_id": null,
        "role": "lead"
      },
      "data": {
        "status": "completed"
      }
    }
  ]
}
```

---

## 4.2 流式 SSE 输出

### 命令

```bash
moma --config config.json --headless --stream run "hello"
```

### 输出规则

每条事件都输出为：

```text
event: <type>
data: <json>

```

最后额外输出一条：

```text
event: response.summary
data: <HeadlessRunResult JSON>
```

### 示例

```text
event: response.created
data: {"type":"response.created","event_id":"evt_001","response_id":"resp_001","session_id":"session-headless","run_id":"run_root_001","sequence":0,"timestamp":"2026-06-05T09:00:00+00:00","agent":{"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},"data":{"status":"created"}}

event: response.output_text.delta
data: {"type":"response.output_text.delta","event_id":"evt_002","response_id":"resp_001","session_id":"session-headless","run_id":"run_root_001","sequence":1,"timestamp":"2026-06-05T09:00:00+00:00","agent":{"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},"data":{"item_id":"item_msg_1","output_index":0,"content_index":0,"delta":"Hello"}}

event: response.completed
data: {"type":"response.completed","event_id":"evt_003","response_id":"resp_001","session_id":"session-headless","run_id":"run_root_001","sequence":2,"timestamp":"2026-06-05T09:00:01+00:00","agent":{"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},"data":{"status":"completed"}}

event: response.summary
data: {"mode":"headless","prompt":"hello","exit_code":0,"message_count":2,"tool_count":0,"subagent_count":0,"events":[...]}
```

---

## 5. 标准响应协议

标准事件模型定义在 `src/protocol/response_events.py`。

## 5.1 顶层统一结构

所有标准事件统一具有以下结构：

```json
{
  "type": "response.output_text.delta",
  "event_id": "evt_xxx",
  "response_id": "resp_xxx",
  "session_id": "session_xxx",
  "run_id": "run_xxx",
  "sequence": 3,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {
    "id": "orchestrator",
    "name": "Orchestrator",
    "kind": "orchestrator",
    "mode": "subagent",
    "parent_agent_id": null,
    "spawned_by_call_id": null,
    "team_id": null,
    "role": "lead"
  },
  "data": {}
}
```

### 顶层字段说明

- `type`: 事件类型
- `event_id`: 当前事件唯一 ID
- `response_id`: 整个响应链路 ID
- `session_id`: 会话 ID
- `run_id`: 本次 agent run ID
- `sequence`: 当前响应内的递增序号
- `timestamp`: ISO 时间戳
- `agent`: 事件来源 agent
- `data`: 具体载荷

### `agent.kind` 可能值

- `orchestrator`
- `subagent`
- `router`
- `team`
- `team_member`
- `system`

### `agent.mode` 可能值

- `router`
- `subagent`
- `all`
- `system`

---

## 5.2 所有标准 `response.*` 类型与示例

当前标准枚举如下：

- `response.created`
- `response.in_progress`
- `response.completed`
- `response.failed`
- `response.output_item.added`
- `response.output_item.done`
- `response.output_text.delta`
- `response.output_text.done`
- `response.reasoning.delta`
- `response.reasoning.done`
- `response.function_call_arguments.delta`
- `response.function_call_arguments.done`
- `response.tool_call.started`
- `response.tool_call.completed`
- `response.tool_call.failed`
- `response.subagent.started`
- `response.subagent.completed`

下面给出逐条示例。

### 5.2.1 `response.created`

```json
{
  "type": "response.created",
  "event_id": "evt_created",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 0,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {
    "id": "orchestrator",
    "name": "Orchestrator",
    "kind": "orchestrator",
    "mode": "subagent",
    "parent_agent_id": null,
    "spawned_by_call_id": null,
    "team_id": null,
    "role": "lead"
  },
  "data": {
    "status": "created",
    "model": "gpt-5.4",
    "provider": "openai"
  }
}
```

### 5.2.2 `response.in_progress`

```json
{
  "type": "response.in_progress",
  "event_id": "evt_progress",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 1,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "status": "in_progress"
  }
}
```

### 5.2.3 `response.completed`

```json
{
  "type": "response.completed",
  "event_id": "evt_completed",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 9,
  "timestamp": "2026-06-05T09:00:01+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "status": "completed",
    "usage": {}
  }
}
```

### 5.2.4 `response.failed`

```json
{
  "type": "response.failed",
  "event_id": "evt_failed",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 9,
  "timestamp": "2026-06-05T09:00:01+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "status": "failed",
    "error": {
      "code": "RUN_ERROR",
      "message": "run failed"
    }
  }
}
```

### 5.2.5 `response.output_item.added`

消息 item 示例：

```json
{
  "type": "response.output_item.added",
  "event_id": "evt_item_added",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 2,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "output_index": 0,
    "item": {
      "id": "item_msg_orchestrator_run_root_001",
      "type": "message",
      "role": "assistant",
      "status": "in_progress"
    }
  }
}
```

function_call item 示例：

```json
{
  "type": "response.output_item.added",
  "event_id": "evt_fc_item_added",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 4,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "output_index": 2,
    "item": {
      "id": "item_fc_call_001",
      "type": "function_call",
      "call_id": "call_001",
      "name": "shell",
      "status": "in_progress"
    }
  }
}
```

### 5.2.6 `response.output_item.done`

```json
{
  "type": "response.output_item.done",
  "event_id": "evt_item_done",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 8,
  "timestamp": "2026-06-05T09:00:01+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "output_index": 2,
    "item": {
      "id": "item_fc_call_001",
      "type": "function_call",
      "call_id": "call_001",
      "name": "shell",
      "status": "completed"
    }
  }
}
```

### 5.2.7 `response.output_text.delta`

```json
{
  "type": "response.output_text.delta",
  "event_id": "evt_text_delta",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 3,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "item_id": "item_msg_orchestrator_run_root_001",
    "output_index": 0,
    "content_index": 0,
    "delta": "你好，我是 MOMA。"
  }
}
```

### 5.2.8 `response.output_text.done`

```json
{
  "type": "response.output_text.done",
  "event_id": "evt_text_done",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 6,
  "timestamp": "2026-06-05T09:00:01+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "item_id": "item_msg_orchestrator_run_root_001",
    "output_index": 0,
    "content_index": 0,
    "text": ""
  }
}
```

### 5.2.9 `response.reasoning.delta`

```json
{
  "type": "response.reasoning.delta",
  "event_id": "evt_reason_delta",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 4,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "item_id": "item_reason_orchestrator_run_root_001",
    "output_index": 1,
    "delta": "先分析用户意图。"
  }
}
```

### 5.2.10 `response.reasoning.done`

```json
{
  "type": "response.reasoning.done",
  "event_id": "evt_reason_done",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 7,
  "timestamp": "2026-06-05T09:00:01+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "item_id": "item_reason_orchestrator_run_root_001",
    "output_index": 1,
    "text": ""
  }
}
```

### 5.2.11 `response.function_call_arguments.delta`

当前 `normalizer` 中已定义该类型，但当前主流程没有实际发出此事件。若未来启用，推荐结构如下：

```json
{
  "type": "response.function_call_arguments.delta",
  "event_id": "evt_args_delta",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 5,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "item_id": "item_fc_call_001",
    "call_id": "call_001",
    "delta": "{\"command\":"
  }
}
```

### 5.2.12 `response.function_call_arguments.done`

这是当前已实际发出的事件。

```json
{
  "type": "response.function_call_arguments.done",
  "event_id": "evt_args_done",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 5,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "item_id": "item_fc_call_001",
    "call_id": "call_001",
    "output_index": 2,
    "name": "shell",
    "arguments": {
      "command": "dir"
    }
  }
}
```

### 5.2.13 `response.tool_call.started`

```json
{
  "type": "response.tool_call.started",
  "event_id": "evt_tool_started",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 6,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "call_id": "call_001",
    "item_id": "item_fc_call_001",
    "name": "shell",
    "arguments": {
      "command": "dir"
    }
  }
}
```

### 5.2.14 `response.tool_call.completed`

```json
{
  "type": "response.tool_call.completed",
  "event_id": "evt_tool_completed",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 7,
  "timestamp": "2026-06-05T09:00:01+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "call_id": "call_001",
    "item_id": "item_fc_call_001",
    "name": "shell",
    "output": {
      "stdout": "file1\nfile2"
    },
    "output_text": "file1\nfile2"
  }
}
```

### 5.2.15 `response.tool_call.failed`

```json
{
  "type": "response.tool_call.failed",
  "event_id": "evt_tool_failed",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "run_root_001",
  "sequence": 7,
  "timestamp": "2026-06-05T09:00:01+00:00",
  "agent": {"id":"orchestrator","name":"Orchestrator","kind":"orchestrator","mode":"subagent","parent_agent_id":null,"spawned_by_call_id":null,"team_id":null,"role":"lead"},
  "data": {
    "call_id": "call_001",
    "item_id": "item_fc_call_001",
    "name": "shell",
    "error": {
      "code": "TOOL_ERROR",
      "message": "command failed"
    }
  }
}
```

### 5.2.16 `response.subagent.started`

```json
{
  "type": "response.subagent.started",
  "event_id": "evt_sub_started",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "subagent-run-001",
  "sequence": 8,
  "timestamp": "2026-06-05T09:00:00+00:00",
  "agent": {
    "id": "writer-agent",
    "name": "writer",
    "kind": "subagent",
    "mode": "subagent",
    "parent_agent_id": "orchestrator",
    "spawned_by_call_id": "call_001",
    "team_id": null,
    "role": "writer"
  },
  "data": {
    "subagent_id": "writer-agent",
    "subagent_name": "writer",
    "parent_agent_id": "orchestrator",
    "spawned_by_call_id": "call_001"
  }
}
```

### 5.2.17 `response.subagent.completed`

```json
{
  "type": "response.subagent.completed",
  "event_id": "evt_sub_completed",
  "response_id": "resp_demo",
  "session_id": "session-demo",
  "run_id": "subagent-run-001",
  "sequence": 9,
  "timestamp": "2026-06-05T09:00:01+00:00",
  "agent": {
    "id": "writer-agent",
    "name": "writer",
    "kind": "subagent",
    "mode": "subagent",
    "parent_agent_id": "orchestrator",
    "spawned_by_call_id": "call_001",
    "team_id": null,
    "role": "writer"
  },
  "data": {
    "subagent_id": "writer-agent",
    "subagent_name": "writer",
    "parent_agent_id": "orchestrator",
    "spawned_by_call_id": "call_001"
  }
}
```

---

## 6. 历史记录 JSON 结构

所有 `run` / `chat` / `headless` / `headless_stream` 执行完成后，都会把原始事件写入 `workspace/history/*.json`。

## 6.1 单条 history 文件示例

```json
{
  "version": 1,
  "entry_id": "hist_20260605T090000Z_ab12cd34",
  "created_at": "2026-06-05T09:00:00+00:00",
  "session_id": "session-a",
  "userspace": "G:\\MOMA\\moma_cli\\llm-host-claw\\.moma_cli",
  "workspace": "G:\\MOMA\\moma_cli\\llm-host-claw\\.moma_cli\\sessions\\session-a",
  "runspace": "G:\\MOMA\\moma_cli\\llm-host-claw\\.moma_cli\\sessions\\session-a\\runs",
  "mode": "chat",
  "prompt": "old prompt",
  "message_count": 2,
  "tool_count": 1,
  "subagent_count": 1,
  "assistant_text_preview": "hello again",
  "events": []
}
```

### `mode` 可能值

- `run`
- `chat`
- `headless`
- `headless_stream`

---

## 7. Web 前端消费建议

如果你要为其他前端适配，建议直接消费两类协议：

## 7.1 在线运行流

- `POST /api/orchestrator/run`
- 解析标准 SSE
- 依据 `type` 做 UI 分发

## 7.2 历史恢复

- `GET /api/web/sessions`
- `GET /api/web/history/latest?session_id=...`

建议渲染策略：

- `response.output_text.delta`：正文流式拼接
- `response.reasoning.delta`：思考区或 metadata 区
- `response.tool_call.*`：工具调用卡片
- `response.subagent.*`：subagent 卡片/右侧栏状态
- `response.completed` / `response.failed`：收尾状态

---

## 8. 常见调用示例

## 8.1 Python 消费 HTTP SSE

```python
import requests

resp = requests.post(
    "http://127.0.0.1:3019/api/orchestrator/run",
    json={"message": "你好", "session_id": "session-python-001"},
    stream=True,
)

for line in resp.iter_lines(decode_unicode=True):
    if line:
        print(line)
```

## 8.2 JavaScript 消费 HTTP SSE

`POST` 型 SSE 通常需要 `fetch()` + ReadableStream：

```javascript
const response = await fetch("http://127.0.0.1:3019/api/orchestrator/run", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    message: "你好",
    session_id: "session-web-001"
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  console.log(decoder.decode(value, { stream: true }));
}
```

## 8.3 将 CLI 当作本地 JSON API

```bash
moma --config config.json --headless run "总结当前目录"
```

## 8.4 将 CLI 当作本地 SSE API

```bash
moma --config config.json --headless --stream run "总结当前目录"
```

---

## 9. 约束与注意事项

- `--headless` 不能和 `--json` 同时使用
- `--headless chat` 必须带 `--prompt`
- `POST /api/orchestrator/run` 当前只返回 SSE，不返回聚合 JSON
- `response.function_call_arguments.delta` 已在协议层预留，但当前主流程默认不发
- `response.summary` 只存在于 CLI `--headless --stream` 输出中，不属于 HTTP `/api/orchestrator/run` 路由返回的一部分
- Web 侧 session/history 接口依赖本地 history 文件，而不是数据库查询

---

## 10. 推荐对接顺序

如果你是要接第三方 UI，建议按下面顺序实现：

1. 先接 `POST /api/orchestrator/run`
2. 完成对 `response.output_text.delta` 的正文流式渲染
3. 再接 `response.tool_call.*`
4. 再接 `response.subagent.*`
5. 最后接 `GET /api/web/sessions` 与 `GET /api/web/history/latest`

这样能最快形成一个可用的对话前端。
