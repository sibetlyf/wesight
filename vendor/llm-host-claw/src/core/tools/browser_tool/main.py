import asyncio
import contextlib
import json
import os
from pathlib import Path
import platform
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from protocol import ExtraInfo, EnVar
from core.tools.browser_tool.browser_toolkit import BrowserUseToolkit, build_browser_orchestrator, new_session_id
from moma_cli.sandbox import current_sandbox_manager


HELP_TEXT = """
可用命令：
  /help                         查看帮助
  /sid                          显示当前 session_id
  /new                          新建对话 session，并关闭当前 session 的浏览器
  /reset_browser                仅重置当前 session 的浏览器，保留聊天历史
  /reset_browser_hard           重置当前 session 的浏览器，并删除该 session 的 profile
  /sessions                     查看当前缓存的浏览器 sessions
  /close_browser                关闭当前 session 的浏览器
  /close_browser_hard           关闭当前 session 的浏览器并删除 profile
  /close_all_browsers           关闭当前进程缓存的全部浏览器
  /tree                         打印 WORKSPACE 目录树
  /config                       显示当前配置文件路径
  /skills                       显示本地脚本型 skills
  /browser <任务>                强制使用 browser-use 直接执行网页任务（仅调试用）
  /browse <任务>                 同 /browser
  /agent <任务>                  强制交给 Orchestrator
  /orchestrator <任务>           同 /agent
  /skill <任务>                  同 /agent
  exit                          退出程序（默认不自动关闭浏览器）
""".strip()


DIRECT_BROWSER_PREFIXES = ("/browser ", "/browse ")
DIRECT_ORCHESTRATOR_PREFIXES = ("/agent ", "/orchestrator ", "/skill ")


def tree_workspace() -> None:
    workspace = os.environ.get("WORKSPACE")
    if not workspace:
        print("[workspace] 环境变量 WORKSPACE 未设置")
        return
    if platform.system() == "Windows":
        os.system('tree /A /F "{}"'.format(workspace))
    else:
        os.system('tree -a "{}"'.format(workspace))


def build_extra(session_id: str) -> ExtraInfo:
    extra = ExtraInfo()
    for field_name in (
        "session_id",
        "agent_session_id",
        "conversation_id",
        "chat_session_id",
    ):
        with contextlib.suppress(Exception):
            setattr(extra, field_name, session_id)
    for attr_name in ("metadata", "extra", "context"):
        with contextlib.suppress(Exception):
            current = getattr(extra, attr_name, None)
            if current is None:
                setattr(extra, attr_name, {"session_id": session_id})
            elif isinstance(current, dict):
                current["session_id"] = session_id
    return extra


async def stream_orchestrator_response(orchestrator, query: str, session_id: str) -> None:
    printed_any = False
    extra = build_extra(session_id)
    async for event in orchestrator.run(query, extra=extra):
        chunks = []
        content = getattr(event, "content", None)
        if isinstance(content, str) and content:
            chunks.append(content)
        metadata = getattr(event, "metadata", None)
        meta_content = getattr(metadata, "content", None) if metadata is not None else None
        if isinstance(meta_content, str) and meta_content and meta_content != content:
            chunks.append(meta_content)
        if not chunks and metadata is not None:
            with contextlib.suppress(Exception):
                dumped = json.dumps(metadata.model_dump(), ensure_ascii=False)
                if dumped and dumped != "{}":
                    chunks.append(dumped)
        emitted = set()
        for chunk in chunks:
            if chunk in emitted:
                continue
            emitted.add(chunk)
            print(chunk, end="", flush=True)
            printed_any = True
    if printed_any:
        print()


async def stream_browser_toolkit_response(
    browser_toolkit: BrowserUseToolkit,
    query: str,
    session_id: str,
) -> None:
    printed_any = False

    async for event in browser_toolkit._astream_browser_events(
        prompt=query,
        run_context=None,
        session_id=session_id,
        use_resume=False,
        max_steps=None,
    ):
        event_type = getattr(event, "event_type", "")
        if event_type not in {"status", "result", "error", "cancelled", "text"}:
            continue
        content = getattr(event, "content", None)
        try:
            text = browser_toolkit._stringify_content(event)
        except Exception:
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)
        if text:
            print(text, flush=True)
            printed_any = True
    if printed_any:
        print()


def _read_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    body = text[3:end].strip()
    data: dict[str, str] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _parse_quoted_terms(text: str) -> list[str]:
    terms: list[str] = []
    buf = ""
    in_quote = False
    quote_chars = {"“": "”", "\"": "\"", "'": "'", "‘": "’"}
    expected_close = ""
    for ch in text:
        if not in_quote and ch in quote_chars:
            in_quote = True
            expected_close = quote_chars[ch]
            buf = ""
            continue
        if in_quote and ch == expected_close:
            term = buf.strip()
            if term:
                terms.append(term)
            in_quote = False
            expected_close = ""
            buf = ""
            continue
        if in_quote:
            buf += ch
    return terms


def _skill_root() -> Path:
    env_root = os.environ.get("SKILLS_ROOT") or os.environ.get("SKILL_ROOT") or os.environ.get("SKILLS_DIR")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[2] / "skills"


def _iter_skill_dirs() -> list[Path]:
    root = _skill_root()
    if not root.exists() or not root.is_dir():
        return []
    return sorted([p for p in root.iterdir() if p.is_dir()])


def _read_skill_manifest(skill_dir: Path) -> tuple[Path, str] | None:
    for name in ("SKILL.md", "skill.md"):
        path = skill_dir / name
        if path.exists() and path.is_file():
            return path, path.read_text(encoding="utf-8", errors="replace")
    return None


def _load_local_script_skills() -> list[dict]:
    """加载可本地执行的单脚本 skill。
    这里不判断“是否需要浏览器”。所有普通自然语言请求仍由 orchestrator 决定工具调用。
    """

    skills: list[dict] = []

    for skill_dir in _iter_skill_dirs():
        manifest = _read_skill_manifest(skill_dir)
        if not manifest:
            continue
        manifest_path, text = manifest
        meta = _read_frontmatter(text)
        skill_name = meta.get("name") or skill_dir.name
        description = meta.get("description") or ""
        scripts = []
        scripts_dir = skill_dir / "scripts"
        if scripts_dir.exists():
            scripts.extend(sorted(scripts_dir.glob("*.py")))
        scripts.extend(sorted(skill_dir.glob("*.py")))
        runnable_scripts = [p for p in scripts if p.name != "__init__.py"]
        if len(runnable_scripts) != 1:
            continue
        terms = [skill_name]
        terms.extend(_parse_quoted_terms(description))
        for line in text.splitlines():
            if "触发词" in line:
                terms.extend(_parse_quoted_terms(line))

        seen = set()
        unique_terms = []
        for term in terms:
            term = term.strip()
            if len(term) < 2 or term in seen:
                continue
            seen.add(term)
            unique_terms.append(term)

        skills.append(
            {
                "skill_name": skill_name,
                "description": description,
                "trigger_terms": unique_terms,
                "manifest": str(manifest_path),
                "script": str(runnable_scripts[0]),
                "timeout": int(os.environ.get("LOCAL_SKILL_TIMEOUT", "1200")),
            }
        )

    return skills


def describe_local_script_skills() -> str:
    payload = {
        "skill_root": str(_skill_root()),
        "skill_count": len(_load_local_script_skills()),
        "skills": _load_local_script_skills(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _query_matches_local_skill(query: str, skill: dict) -> bool:
    q = (query or "").lower()
    return any(term.lower() in q for term in skill.get("trigger_terms", []))


async def _run_python_script(script: Path, *, timeout: int) -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("RUNSPACE", os.environ.get("RUNSPACE") or str(Path.cwd() / "runs"))
    env["JIUTIAN_HEADLESS"] = env.get("JIUTIAN_HEADLESS_OVERRIDE", "0")
    # 本地测试入口默认有头运行，方便用户在九天登录页手动登录；发现流程保持稳定顺序：接口拿模型 ID，再逐个打开详情/API参考页。
    # 避免 PowerShell 会话里残留 JIUTIAN_DISCOVERY_MODE=click 导致再次走失败的纯点击路径。
    env["JIUTIAN_DISCOVERY_MODE"] = env.get("JIUTIAN_DISCOVERY_MODE_OVERRIDE", "network")
    Path(env["RUNSPACE"]).mkdir(parents=True, exist_ok=True)
    print(f"[skill local] script: {script}", flush=True)
    print(f"[skill local] RUNSPACE: {env['RUNSPACE']}", flush=True)

    prepared = current_sandbox_manager().prepare_spawn(
        argv=[sys.executable, str(script)],
        cwd=str(script.parent),
        env=env,
    )

    proc = await asyncio.create_subprocess_exec(
        *prepared.argv,
        cwd=prepared.cwd,
        env=prepared.env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    async def pump_output() -> None:
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            print(line.decode("utf-8", errors="replace"), end="", flush=True)

    pump_task = asyncio.create_task(pump_output())
    try:
        rc = await asyncio.wait_for(proc.wait(), timeout=timeout)
        await pump_task
        return int(rc or 0)
    except asyncio.TimeoutError:
        proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        with contextlib.suppress(Exception):
            await pump_task
        print(f"[skill local] timeout after {timeout}s", flush=True)
        return 124


async def try_run_local_script_skill(query: str) -> bool:
    for skill in _load_local_script_skills():
        if not _query_matches_local_skill(query, skill):
            continue
        print(f"[route] local script skill: {skill['skill_name']}", flush=True)
        rc = await _run_python_script(
            Path(skill["script"]),
            timeout=int(skill.get("timeout") or 1200),
        )
        if rc == 0:
            print("[skill local] completed", flush=True)
        else:
            print(f"[skill local] failed with exit code {rc}", flush=True)
        return True
    return False


def resolve_route(query: str) -> tuple[str, str]:
    text = (query or "").strip()
    lower = text.lower()
    for prefix in DIRECT_BROWSER_PREFIXES:
        if lower.startswith(prefix):
            return "browser", text[len(prefix):].strip()
    for prefix in DIRECT_ORCHESTRATOR_PREFIXES:
        if lower.startswith(prefix):
            return "orchestrator", text[len(prefix):].strip()
    return "orchestrator", text


async def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    envar = EnVar.from_env()
    envar.record_id = f"local_{uuid.uuid4().hex}"
    envar.user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    envar.authorization = os.getenv("AUTHORIZATION", "EMPTY")
    orchestrator_kwargs = {
        "envar": envar,
        "base_url": os.getenv("BROWSER_TOOL_DEMO_BASE_URL", "https://example.com/v1"),
        "model_id": os.getenv("BROWSER_TOOL_DEMO_MODEL", "deepseek-v4-pro"),
    }
    orchestrator, resolved_config_path, browser_toolkit = build_browser_orchestrator(config_path, **orchestrator_kwargs)
    session_id = new_session_id()
    print(f"[session] {session_id}")
    print(f"[config] {resolved_config_path}")
    print(f"[record_id] {envar.record_id or '(empty)'}")
    print(f"[user_id] {envar.user_id or '(empty)'}")
    print("[auth] authorization loaded from environment")
    print("输入 /help 查看命令，输入 exit 退出。")

    try:
        while True:
            try:
                query = input("user input: ").strip()
            except EOFError:
                print()
                break
            if not query:
                continue
            lower_query = query.lower()
            if lower_query in {"exit", "quit"}:
                break
            if query == "/help":
                print(HELP_TEXT)
                continue
            if query == "/sid":
                print(f"[session] {session_id}")
                continue
            if query == "/config":
                print(f"[config] {resolved_config_path}")
                print(f"[record_id] {envar.record_id or '(empty)'}")
                print(f"[user_id] {envar.user_id or '(empty)'}")
                print("[auth] authorization loaded from environment")
                continue
            if query == "/skills":
                print(describe_local_script_skills())
                continue
            if query == "/tree":
                tree_workspace()
                continue
            if query == "/sessions":
                if browser_toolkit is None:
                    print("[browser toolkit] not found")
                else:
                    print(browser_toolkit.list_browser_sessions())
                continue
            if query == "/close_browser":
                if browser_toolkit is None:
                    print("[browser toolkit] not found")
                else:
                    print(await browser_toolkit.close_browser_for_session(session_id, delete_profile=False))
                continue
            if query == "/close_browser_hard":
                if browser_toolkit is None:
                    print("[browser toolkit] not found")
                else:
                    print(await browser_toolkit.close_browser_for_session(session_id, delete_profile=True))
                continue
            if query == "/close_all_browsers":
                if browser_toolkit is None:
                    print("[browser toolkit] not found")
                else:
                    print(await browser_toolkit.close_all_browsers(delete_profiles=False))
                continue
            if query == "/reset_browser":
                if browser_toolkit is None:
                    print("[browser toolkit] not found")
                else:
                    print(await browser_toolkit.close_browser_for_session(session_id, delete_profile=False))
                continue
            if query == "/reset_browser_hard":
                if browser_toolkit is None:
                    print("[browser toolkit] not found")
                else:
                    print(await browser_toolkit.close_browser_for_session(session_id, delete_profile=True))
                continue
            if query == "/new":
                if browser_toolkit is not None:
                    print(await browser_toolkit.close_browser_for_session(session_id, delete_profile=False))
                session_id = new_session_id()
                print(f"[new session] {session_id}")
                continue
            route, routed_query = resolve_route(query)
            if route == "orchestrator" and await try_run_local_script_skill(routed_query):
                continue
            if not routed_query:
                if route == "browser":
                    print("用法：/browser <要让 browser-use 执行的网页任务>")
                else:
                    print("用法：/agent <要交给 Orchestrator 的任务>")
                continue
            if route == "browser":
                if browser_toolkit is None:
                    print("[browser toolkit] not found")
                else:
                    print("[route] forced browser-use")
                    await stream_browser_toolkit_response(browser_toolkit, routed_query, session_id)
            else:
                print("[route] orchestrator skill router")
                await stream_orchestrator_response(orchestrator, routed_query, session_id)
    except KeyboardInterrupt:
        print("\n[interrupted]")
    finally:
        if isinstance(browser_toolkit, BrowserUseToolkit):
            print("[browser toolkit] 保留当前浏览器实例；如需关闭，请使用 /close_browser、/close_browser_hard 或 /close_all_browsers。")


if __name__ == "__main__":
    asyncio.run(main())
