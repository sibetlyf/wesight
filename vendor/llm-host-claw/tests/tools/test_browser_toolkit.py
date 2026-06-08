import asyncio
import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from agno.agent import Agent
from agno.run.agent import ToolCallCompletedEvent

from src.core.tools.browser_tool.browser_toolkit import (
    BrowserAgentEvent,
    BrowserConversationState,
    BrowserUseToolkit,
)
from src.configs.browse_use import build_jt_openai_like_model


class _FakeCfg:
    toolkit_name = "browser_use"
    toolkit_instructions = "用于测试"
    register_task_tools = True
    keep_alive = True
    max_steps = 5
    emit_step_summary = True
    emit_step_text = True
    max_actions_per_step = None
    max_failures = 4
    use_vision = False
    vision_detail_level = None
    flash_mode = False
    use_thinking = False
    step_timeout = None
    llm_timeout = None
    directly_open_url = None
    final_response_after_failure = True
    save_conversation_path = None
    available_file_paths = None
    sensitive_data = None
    extend_system_message = None
    override_system_message = None
    initial_actions = None
    generate_gif = None
    calculate_cost = None
    browser_factory = None
    agent_factory = None
    browser_kwargs = {}
    agent_kwargs = {}

    cdp_url = None
    headless = True
    storage_state = None
    profile_directory = None
    user_data_dir = None
    allowed_domains = None
    prohibited_domains = None
    executable_path = None
    channel = None
    proxy = None
    viewport = None
    window_size = None
    window_position = None
    no_viewport = None
    minimum_wait_page_load_time = None
    wait_for_network_idle_page_load_time = None
    wait_between_actions = None
    trace_dir = None
    record_video_dir = None
    record_har_path = None
    args = None
    chromium_args = None
    runtime_user = ""
    runtime_record_id = ""
    runtime_authorization = ""

    def validate(self):
        return None

    def build_inner_llm(self):
        return SimpleNamespace(provider="openai", model="qwen-test")

    def get_model_profile(self):
        return {
            "use_vision": False,
            "use_thinking": False,
            "max_actions_per_step": 1,
            "flash_mode": False,
            "final_response_after_failure": True,
        }


@pytest.fixture(autouse=True)
def clear_browser_toolkit_globals():
    BrowserUseToolkit._GLOBAL_ACTIVE_RUNS.clear()
    BrowserUseToolkit._GLOBAL_RECENT_RUNS.clear()
    BrowserUseToolkit._GLOBAL_SESSION_STATES.clear()
    BrowserUseToolkit._GLOBAL_SESSION_LOCKS.clear()
    yield
    BrowserUseToolkit._GLOBAL_ACTIVE_RUNS.clear()
    BrowserUseToolkit._GLOBAL_RECENT_RUNS.clear()
    BrowserUseToolkit._GLOBAL_SESSION_STATES.clear()
    BrowserUseToolkit._GLOBAL_SESSION_LOCKS.clear()


@pytest.fixture
def cfg(tmp_path):
    c = _FakeCfg()
    c.user_data_dir = str(tmp_path / "profiles")
    return c


def _make_envar(user="u1", record_id="r1", authorization="auth1", workspace="", runspace=""):
    return SimpleNamespace(
        workspace=workspace,
        runspace=runspace,
        user_id=user,
        record_id=record_id,
        authorization=authorization,
    )


@pytest.fixture
def toolkit(cfg):
    return BrowserUseToolkit(cfg=cfg, envar=_make_envar())


def test_instantiation_registers_current_tools(toolkit):
    assert toolkit.name == "browser_use"
    names = [f.name for f in toolkit.functions.values()]
    assert "run_browser_agent" in names
    assert "cancel_task" in names
    assert "get_task_status" in names
    assert "list_active_tasks" in names
    assert "list_browser_sessions" in names


def test_runtime_fields_are_synced_to_cfg(toolkit):
    assert toolkit.cfg.runtime_user == "u1"
    assert toolkit.cfg.runtime_record_id == "r1"
    assert toolkit.cfg.runtime_authorization == "auth1"


def test_register_task_tools_disabled(cfg):
    cfg.register_task_tools = False
    t = BrowserUseToolkit(cfg=cfg, envar=_make_envar())
    names = [f.name for f in t.functions.values()]
    assert names == ["run_browser_agent"]


def test_list_active_tasks_initial(toolkit):
    data = json.loads(toolkit.list_active_tasks())
    assert data == {"active_count": 0, "tasks": []}


def test_list_browser_sessions_initial(toolkit):
    data = json.loads(toolkit.list_browser_sessions())
    assert data == {"session_count": 0, "sessions": []}


def test_get_task_status_not_found(toolkit):
    data = json.loads(toolkit.get_task_status("missing"))
    assert data == {"task_id": "missing", "status": "not_found"}


def test_get_task_status_recent_run(toolkit):
    toolkit._recent_runs["done1"] = {
        "task_id": "done1",
        "session_id": "sess1",
        "prompt": "hello",
        "started_at": "now",
        "status": "completed",
        "latest_step": 2,
        "last_url": "https://example.com",
    }
    data = json.loads(toolkit.get_task_status("done1"))
    assert data["task_id"] == "done1"
    assert data["session_id"] == "sess1"
    assert data["status"] == "completed"
    assert data["last_url"] == "https://example.com"


def test_cancel_task_not_found(toolkit):
    data = json.loads(toolkit.cancel_task("missing"))
    assert data == {"task_id": "missing", "status": "not_found"}


def test_cancel_task_running(toolkit):
    class _FakeTask:
        def __init__(self):
            self._done = False
            self.cancel_called = False

        def done(self):
            return self._done

        def cancel(self):
            self.cancel_called = True

    task = _FakeTask()
    toolkit._active_runs["t1"] = {
        "task_id": "t1",
        "session_id": "sess1",
        "prompt": "hello",
        "started_at": "now",
        "status": "running",
        "latest_step": 0,
        "last_url": None,
        "asyncio_task": task,
    }
    data = json.loads(toolkit.cancel_task("t1"))
    assert data == {"task_id": "t1", "status": "cancelling"}
    assert task.cancel_called is True
    assert toolkit._active_runs["t1"]["status"] == "cancelling"


def test_resolve_session_id(toolkit):
    rc = SimpleNamespace(session_id="sess-from-context")
    assert toolkit._resolve_session_id(run_context=rc, session_id=None) == "sess-from-context"
    assert toolkit._resolve_session_id(run_context=rc, session_id="explicit") == "sess-from-context"


def test_get_session_lock_same_object(toolkit):
    lock1 = toolkit._get_session_lock("abc")
    lock2 = toolkit._get_session_lock("abc")
    assert lock1 is lock2


def test_session_user_data_dir_uses_cfg_base(toolkit, cfg):
    out = toolkit._session_user_data_dir("sess-x")
    assert Path(out).parent == Path(cfg.user_data_dir).resolve()
    assert out.endswith(os.path.join(Path(cfg.user_data_dir).name, "sess-x"))


def test_touch_state_updates_state(toolkit):
    state = BrowserConversationState(session_id="s1", browser=None, agent=None, llm=None)
    toolkit._touch_state(state, last_url="https://a.com", last_title="A", latest_step=3)
    assert state.last_url == "https://a.com"
    assert state.last_title == "A"
    assert state.latest_step == 3
    assert state.status == "ready"


def test_state_is_alive(toolkit):
    async def _run():
        state1 = BrowserConversationState(
            session_id="s1",
            browser=SimpleNamespace(is_connected=lambda: True),
            agent=None,
            llm=None,
        )
        state2 = BrowserConversationState(
            session_id="s2",
            browser=SimpleNamespace(connected=False),
            agent=None,
            llm=None,
        )
        assert await toolkit._state_is_alive(state1) is True
        assert await toolkit._state_is_alive(state2) is False

    asyncio.run(_run())


def test_close_session_browser_not_found(toolkit):
    async def _run():
        data = json.loads(await toolkit.close_session_browser("missing"))
        assert data == {"session_id": "missing", "status": "not_found"}

    asyncio.run(_run())


def test_close_browser_for_session_fallback(toolkit):
    async def _run():
        async def _fake_close(session_id, delete_profile=False):
            if session_id == "missing":
                return json.dumps({"session_id": session_id, "status": "not_found"}, ensure_ascii=False)
            return json.dumps({"session_id": session_id, "status": "closed"}, ensure_ascii=False)

        toolkit.close_session_browser = _fake_close
        toolkit._session_states["sess-recent"] = BrowserConversationState(
            session_id="sess-recent",
            browser=None,
            agent=None,
            llm=None,
        )
        data = json.loads(await toolkit.close_browser_for_session("missing", delete_profile=False))
        assert data["requested_session_id"] == "missing"
        assert data["requested_status"] == "not_found"
        assert data["fallback_session_id"] == "sess-recent"

    asyncio.run(_run())


def test_close_all_browsers_empty(toolkit):
    async def _run():
        data = json.loads(await toolkit.close_all_browsers())
        assert data == {"status": "ok", "closed": [], "failed": []}

    asyncio.run(_run())


def test_to_agno_event_status(toolkit):
    run_context = SimpleNamespace(session_id="sess", run_id="run1")
    event = BrowserAgentEvent(event_type="status", content="started", metadata={"task_id": "t1", "session_id": "sess"})
    out = toolkit._to_agno_event(run_context, event)
    assert out.type == "content"
    assert out.content == "started"
    assert out.session_id == "sess"
    assert out.run_id == "run1"


def test_to_agno_event_step_start(toolkit):
    run_context = SimpleNamespace(session_id="sess", run_id="run1")
    event = BrowserAgentEvent(
        event_type="step_start",
        content={"step": 1, "task": "search"},
        metadata={"task_id": "t1", "step": 1, "session_id": "sess"},
    )
    out = toolkit._to_agno_event(run_context, event)
    assert out.type == "document"
    assert out.session_id == "sess"


def test_to_agno_event_result(toolkit):
    run_context = SimpleNamespace(session_id="sess", run_id="run1")
    event = BrowserAgentEvent(
        event_type="result",
        content={"ok": True, "answer": "done"},
        metadata={"task_id": "t1", "session_id": "sess"},
    )
    out = toolkit._to_agno_event(run_context, event)
    assert out.type == "content"
    assert json.loads(out.content) == {"ok": True, "answer": "done"}


def test_run_browser_agent(toolkit):
    async def _run():
        run_context = SimpleNamespace(session_id="sess", run_id="run1")

        async def _fake_stream(**kwargs):
            yield BrowserAgentEvent(event_type="status", content="started", metadata={"task_id": "t1", "session_id": "sess"})
            yield BrowserAgentEvent(event_type="result", content={"ok": True}, metadata={"task_id": "t1", "session_id": "sess"})

        toolkit._astream_browser_events = _fake_stream
        events = []
        async for ev in toolkit.run_browser_agent(run_context, "do it"):
            events.append(ev)

        assert len(events) == 1
        assert events[0].type == "content"
        assert json.loads(events[0].content) == {"ok": True}

    asyncio.run(_run())


def test_jsonable(toolkit):
    class _Obj:
        def __init__(self):
            self.x = 1
            self.y = "ok"

    out = toolkit._jsonable({"a": [1, 2], "b": _Obj()})
    assert out["a"] == [1, 2]
    assert out["b"]["x"] == 1
    assert out["b"]["y"] == "ok"


def test_infer_step_no_from_attr(toolkit):
    agent = SimpleNamespace(current_step=3)
    assert toolkit._infer_step_no(agent) == 3


def test_infer_step_no_from_history(toolkit):
    history = SimpleNamespace(model_actions=lambda: [{"a": 1}, {"b": 2}])
    agent = SimpleNamespace(history=history)
    assert toolkit._infer_step_no(agent) == 2


def test_render_step_text(toolkit):
    snapshot = {
        "step": 2,
        "url": "https://www.baidu.com/",
        "title": "百度一下",
        "latest_action": {"navigate": {"url": "https://www.baidu.com", "new_tab": False}},
        "latest_result": {"ok": True},
        "thoughts": {"next_goal": "search openclaw"},
    }
    text = toolkit._render_step_text(snapshot)
    assert "Step 2" in text
    assert "https://www.baidu.com/" in text
    assert "百度一下" in text


def test_history_to_result(toolkit):
    history = SimpleNamespace(
        final_result=lambda: {"answer": "done"},
        urls=lambda: ["https://www.baidu.com/"],
        model_actions=lambda: [{"navigate": {"url": "https://www.baidu.com"}}],
        model_thoughts=lambda: [{"next_goal": "search"}],
        model_outputs=lambda: [{"action": [{"navigate": {"url": "https://www.baidu.com"}}]}],
        extracted_content=lambda: ["ok"],
    )
    out = toolkit._history_to_result(history)
    assert out["final_result"] == {"answer": "done"}
    assert out["urls"] == ["https://www.baidu.com/"]
    assert out["extracted_content"] == ["ok"]


def test_collect_agent_snapshot(toolkit):
    async def _run():
        history = SimpleNamespace(
            model_actions=lambda: [{"navigate": {"url": "https://www.baidu.com"}}],
            model_outputs=lambda: [{"action": [{"navigate": {"url": "https://www.baidu.com"}}]}],
            model_thoughts=lambda: [{"next_goal": "search"}],
            urls=lambda: ["https://www.baidu.com/"],
        )
        page = SimpleNamespace(url="https://www.baidu.com/", title=lambda: "百度一下")
        agent = SimpleNamespace(current_step=1, page=page, history=history)
        out = await toolkit._collect_agent_snapshot(agent)
        assert out["step"] == 1
        assert out["url"] == "https://www.baidu.com/"
        assert out["title"] == "百度一下"
        assert out["latest_action"] == {"navigate": {"url": "https://www.baidu.com"}}

    asyncio.run(_run())


def test_build_browser_uses_factory(cfg):
    async def _run():
        browser = SimpleNamespace(name="browser")
        captured = {}

        async def _factory(session_id, cfg, user_data_dir):
            captured["session_id"] = session_id
            captured["cfg"] = cfg
            captured["user_data_dir"] = user_data_dir
            return browser

        cfg.browser_factory = _factory
        toolkit = BrowserUseToolkit(cfg=cfg, envar=_make_envar())
        out = await toolkit._build_browser("sess-a")
        assert out is browser
        assert captured["session_id"] == "sess-a"
        assert captured["cfg"] is cfg
        assert captured["user_data_dir"].endswith(os.path.join(Path(cfg.user_data_dir).name, "sess-a"))

    asyncio.run(_run())


def test_build_agent_uses_factory(cfg):
    async def _run():
        agent = SimpleNamespace(name="agent")

        async def _factory(prompt, llm, browser, browser_session, cfg):
            assert prompt == "task"
            assert llm.model == "qwen-test"
            assert browser.name == "browser"
            assert browser_session.name == "browser"
            assert cfg is cfg_ref
            return agent

        cfg_ref = cfg
        cfg.agent_factory = _factory
        toolkit = BrowserUseToolkit(cfg=cfg, envar=_make_envar())
        out = await toolkit._build_agent(
            prompt="task",
            llm=SimpleNamespace(provider="openai", model="qwen-test"),
            browser_handle=SimpleNamespace(name="browser"),
        )
        assert out is agent

    asyncio.run(_run())


def test_append_followup_task_prefers_add_new_task(toolkit):
    async def _run():
        called = {}

        class _Agent:
            async def add_new_task(self, prompt):
                called["prompt"] = prompt

        state = BrowserConversationState(session_id="s", browser=SimpleNamespace(), agent=_Agent(), llm=SimpleNamespace())
        await toolkit._append_followup_task(state, "follow up")
        assert called["prompt"] == "follow up"

    asyncio.run(_run())


def test_append_followup_task_rebuilds_when_needed(toolkit):
    async def _run():
        rebuilt = SimpleNamespace(name="rebuilt")

        async def _fake_build_agent(prompt, llm, browser_handle):
            assert prompt == "follow up"
            assert browser_handle.name == "browser"
            return rebuilt

        toolkit._build_agent = _fake_build_agent
        state = BrowserConversationState(
            session_id="s",
            browser=SimpleNamespace(name="browser"),
            agent=SimpleNamespace(),
            llm=SimpleNamespace(),
        )
        await toolkit._append_followup_task(state, "follow up")
        assert state.agent is rebuilt

    asyncio.run(_run())


def test_ensure_session_state_create_and_reuse(toolkit):
    async def _run():
        browser = SimpleNamespace(is_connected=lambda: True)
        built_prompts = []
        built_agents = []

        async def _fake_build_browser(session_id):
            assert session_id == "sess-x"
            return browser

        async def _fake_build_agent(prompt, llm, browser_handle):
            built_prompts.append(prompt)
            assert browser_handle is browser
            agent = SimpleNamespace(name=f"agent-{len(built_prompts)}")
            built_agents.append(agent)
            return agent

        toolkit._build_browser = _fake_build_browser
        toolkit._build_agent = _fake_build_agent
        state1, browser_reused1, agent_reused1 = await toolkit._ensure_session_state(
            "sess-x", initial_prompt="task one", reuse_agent=False
        )
        assert browser_reused1 is False
        assert agent_reused1 is False
        assert state1.browser is browser
        assert state1.agent is built_agents[0]
        assert toolkit._session_states["sess-x"] is state1

        state2, browser_reused2, agent_reused2 = await toolkit._ensure_session_state(
            "sess-x", initial_prompt="task two", reuse_agent=True
        )
        assert browser_reused2 is True
        assert agent_reused2 is True
        assert state2 is state1

        state3, browser_reused3, agent_reused3 = await toolkit._ensure_session_state(
            "sess-x", initial_prompt="task three", reuse_agent=False
        )
        assert browser_reused3 is True
        assert agent_reused3 is False
        assert state3 is state1
        assert state3.agent is built_agents[1]
        assert built_prompts == ["task one", "task three"]

    asyncio.run(_run())


def test_shutdown_and_close_session_browser(toolkit, tmp_path):
    async def _run():
        called = {"closed": False}

        class _Browser:
            async def close(self):
                called["closed"] = True

        state = BrowserConversationState(
            session_id="sess-z",
            browser=_Browser(),
            agent=SimpleNamespace(),
            llm=SimpleNamespace(),
            user_data_dir=str(tmp_path / "profile-sess-z"),
        )
        toolkit._session_states["sess-z"] = state
        data = json.loads(await toolkit.close_session_browser("sess-z", delete_profile=True))
        assert data["status"] == "closed"
        assert data["session_id"] == "sess-z"
        assert called["closed"] is True
        assert "sess-z" not in toolkit._session_states

    asyncio.run(_run())


def test_should_reset_session(toolkit):
    assert toolkit._should_reset_session(RuntimeError("browser has been closed")) is True
    assert toolkit._should_reset_session(RuntimeError("other failure")) is False


def test_looks_like_premature_completion(toolkit):
    assert toolkit._looks_like_premature_completion(
        {
            "final_result": None,
            "urls": ["https://www.baidu.com/"],
            "actions": [{"navigate": {"url": "https://www.baidu.com", "new_tab": False}}],
            "outputs": [],
            "extracted_content": [],
        },
        prompt="search openclaw",
    ) is True
    assert toolkit._looks_like_premature_completion(
        {
            "final_result": {"ok": True},
            "urls": ["https://www.baidu.com/s?wd=openclaw"],
            "actions": [{"navigate": {"url": "https://www.baidu.com/s?wd=openclaw", "new_tab": False}}],
            "outputs": [{"action": [{"navigate": {"url": "https://www.baidu.com/s?wd=openclaw"}}]}],
            "extracted_content": ["openclaw result"],
        },
        prompt="search openclaw",
    ) is False


def test_astream_browser_events_success(toolkit):
    async def _run():
        history = SimpleNamespace(
            final_result=lambda: {"answer": "done"},
            urls=lambda: ["https://www.baidu.com/s?wd=openclaw"],
            model_actions=lambda: [{"navigate": {"url": "https://www.baidu.com/s?wd=openclaw", "new_tab": False}}],
            model_thoughts=lambda: [{"next_goal": "open results"}],
            model_outputs=lambda: [{"action": [{"navigate": {"url": "https://www.baidu.com/s?wd=openclaw"}}]}],
            extracted_content=lambda: ["openclaw results page"],
        )

        class _FakeAgent:
            def __init__(self):
                self.task = "search openclaw"
                self.page = SimpleNamespace(url="https://www.baidu.com/s?wd=openclaw", title=lambda: "openclaw_百度搜索")
                self.history = history
                self.current_step = 1

            async def run(self, max_steps=None, on_step_start=None, on_step_end=None):
                assert max_steps == toolkit.cfg.max_steps
                if on_step_start:
                    await on_step_start(self)
                if on_step_end:
                    await on_step_end(self)
                return history

        state = BrowserConversationState(
            session_id="cli_session",
            browser=SimpleNamespace(name="browser"),
            agent=_FakeAgent(),
            llm=SimpleNamespace(provider="openai", model="qwen-test"),
        )

        prepared_prompt = toolkit._prepare_agent_task("search openclaw")

        async def _fake_ensure(session_id, initial_prompt, reuse_agent=True):
            assert session_id == "cli_session"
            assert initial_prompt == prepared_prompt
            assert reuse_agent is False
            toolkit._session_states[session_id] = state
            return state, False, False

        toolkit._ensure_session_state = _fake_ensure
        events = []
        async for ev in toolkit._astream_browser_events(prompt="search openclaw", session_id="cli_session"):
            events.append(ev)
        assert len(events) >= 4
        assert events[0].event_type == "status"
        assert events[0].content["browser_reused"] is False
        assert any(ev.event_type == "step_start" for ev in events)
        assert any(ev.event_type == "step_end" for ev in events)
        assert any(ev.event_type == "text" for ev in events)
        assert events[-1].event_type == "result"
        assert events[-1].metadata["task_id"].startswith("cli_session_")
        assert toolkit._active_runs == {}
        assert len(toolkit._recent_runs) == 1
        recent = next(iter(toolkit._recent_runs.values()))
        assert recent["status"] == "completed"
        assert state.turn_count == 1
        assert state.last_url == "https://www.baidu.com/s?wd=openclaw"

    asyncio.run(_run())


def test_astream_browser_events_premature_completion_error(toolkit):
    async def _run():
        history = SimpleNamespace(
            final_result=lambda: {"answer": "done"},
            urls=lambda: ["https://www.baidu.com/"],
            model_actions=lambda: [{"navigate": {"url": "https://www.baidu.com", "new_tab": False}}],
            model_thoughts=lambda: [{"next_goal": "search"}],
            model_outputs=lambda: [{"action": [{"navigate": {"url": "https://www.baidu.com"}}]}],
            extracted_content=lambda: [],
        )

        class _FakeAgent:
            def __init__(self):
                self.task = "search openclaw"
                self.page = SimpleNamespace(url="https://www.baidu.com/", title=lambda: "百度一下")
                self.history = history
                self.current_step = 1

            async def run(self, **kwargs):
                return self.history

        state = BrowserConversationState(
            session_id="cli_session",
            browser=SimpleNamespace(name="browser"),
            agent=_FakeAgent(),
            llm=SimpleNamespace(provider="openai", model="qwen-test"),
        )

        prepared_prompt = toolkit._prepare_agent_task("search openclaw")

        async def _fake_ensure(session_id, initial_prompt, reuse_agent=True):
            assert initial_prompt == prepared_prompt
            assert reuse_agent is False
            toolkit._session_states[session_id] = state
            return state, False, False

        toolkit._ensure_session_state = _fake_ensure
        events = []
        async for ev in toolkit._astream_browser_events(prompt="search openclaw", session_id="cli_session"):
            events.append(ev)
        assert any(ev.event_type == "error" for ev in events)
        error_event = next(ev for ev in events if ev.event_type == "error")
        assert "提前结束" in error_event.content["error"]

    asyncio.run(_run())


def test_astream_browser_events_error(toolkit):
    async def _run():
        class _FakeAgent:
            async def run(self, **kwargs):
                raise RuntimeError("boom")

        state = BrowserConversationState(
            session_id="sess",
            browser=SimpleNamespace(name="browser"),
            agent=_FakeAgent(),
            llm=SimpleNamespace(provider="openai", model="qwen-test"),
        )

        async def _fake_ensure(session_id, initial_prompt, reuse_agent=True):
            toolkit._session_states[session_id] = state
            return state, False, False

        toolkit._ensure_session_state = _fake_ensure
        events = []
        async for ev in toolkit._astream_browser_events(prompt="x", session_id="sess"):
            events.append(ev)
        assert events, "异常流至少应返回一个事件"
        assert any(ev.event_type == "error" for ev in events)
        error_event = next(ev for ev in events if ev.event_type == "error")
        assert "boom" in error_event.content["error"]
        assert len(toolkit._recent_runs) == 1
        recent = next(iter(toolkit._recent_runs.values()))
        assert recent["status"] == "failed"

    asyncio.run(_run())


def test_astream_browser_events_cancelled(toolkit):
    async def _run():
        class _FakeAgent:
            async def run(self, **kwargs):
                raise asyncio.CancelledError()

        state = BrowserConversationState(
            session_id="sess",
            browser=SimpleNamespace(name="browser"),
            agent=_FakeAgent(),
            llm=SimpleNamespace(provider="openai", model="qwen-test"),
        )

        async def _fake_ensure(session_id, initial_prompt, reuse_agent=True):
            toolkit._session_states[session_id] = state
            return state, False, False

        toolkit._ensure_session_state = _fake_ensure
        events = []
        async for ev in toolkit._astream_browser_events(prompt="x", session_id="sess"):
            events.append(ev)
        assert any(ev.event_type == "cancelled" for ev in events)
        assert len(toolkit._recent_runs) == 1
        recent = next(iter(toolkit._recent_runs.values()))
        assert recent["status"] == "cancelled"

    asyncio.run(_run())


@pytest.fixture
def browser_toolkit_tools():
    cfg = _FakeCfg()
    cfg.runtime_user = os.getenv("USER_ID", "")
    cfg.runtime_record_id = os.getenv("RECORD_ID", "")
    cfg.runtime_authorization = os.getenv("AUTHORIZATION", "")
    toolkit = BrowserUseToolkit(
        cfg=cfg,
        envar=_make_envar(
            user=cfg.runtime_user or "user1",
            record_id=cfg.runtime_record_id or "record1",
            authorization=cfg.runtime_authorization or "auth1",
        ),
    )

    async def _fake_stream(**kwargs):
        yield BrowserAgentEvent(
            event_type="status",
            content="browser-use agent 已启动",
            metadata={"task_id": "t_browser_1", "session_id": kwargs.get("session_id", "sess")},
        )
        yield BrowserAgentEvent(
            event_type="result",
            content={"ok": True, "summary": "mock browser task finished"},
            metadata={"task_id": "t_browser_1", "session_id": kwargs.get("session_id", "sess")},
        )

    toolkit._astream_browser_events = _fake_stream
    return toolkit


def test_agno_agent_with_browser_tool(browser_toolkit_tools):
    async def _run():
        base_url = os.getenv("JIUTIAN_BASE_URL", "")
        model_id = os.getenv("JIUTIAN_MODEL_ID", "")
        api_key = os.getenv("JIUTIAN_API_KEY", "")
        user = os.getenv("USER_ID", "")
        record_id = os.getenv("RECORD_ID", "")
        authorization = os.getenv("AUTHORIZATION", "") or api_key
        if not (base_url and model_id and api_key and user and record_id and authorization):
            pytest.skip("未设置完整的九天集成测试环境变量，跳过真实 Agent 工具触发测试")
        model = build_jt_openai_like_model(
            model_name=model_id,
            base_url=base_url,
            api_key=api_key,
            user=user,
            record_id=record_id,
            enable_thinking=False,
        )
        agent = Agent(
            model=model,
            tools=[browser_toolkit_tools],
            instructions=(
                "你是一个擅长浏览器自动化的智能体。"
                "当用户要求你打开网页、搜索内容、浏览页面、读取网页信息时，"
                "优先调用 browser_use 工具，不要只进行口头回答。"
            ),
            user_id="user1",
            debug_mode=True,
            add_history_to_context=True,
            stream_events=True,
            telemetry=False,
        )
        session_id = str(uuid.uuid4())
        tool_called = False

        async for event in agent.arun(
            "请你打开百度搜索引擎，搜索 openclaw，并用 browser_use 工具完成这件事",
            session_id=session_id,
            stream=True,
            yield_run_output=True,
            debug_mode=True,
        ):
            if isinstance(event, ToolCallCompletedEvent):
                tool_called = True

        assert tool_called, "browser_use 工具未被触发"

    asyncio.run(_run())
