from __future__ import annotations

import contextlib
import inspect
import json
import os
import re
from urllib.parse import urlparse
from typing import Any, Callable, Dict, List, Optional, Literal

from agno.models.openai.like import OpenAILike
from .common import ToolkitConfigBase


def _browser_agent_no_thinking_extra_body(base_url: str) -> Dict[str, Any]:
    """Return the mandatory no-thinking payload for every browser-agent LLM request.

    This deliberately has no YAML/config switch:
    - China Mobile / 10086 OpenAI-compatible gateways use their documented extension
      fields and always disable moderation + reasoning for browser automation.
    - Other OpenAI-compatible DeepSeek-style gateways use ``thinking.type=disabled``.

    If a future external gateway rejects the DeepSeek-style field, extend this
    endpoint mapping in code; do not re-enable thinking in browser-agent tasks.
    """
    try:
        host = (urlparse(str(base_url or "")).hostname or "").lower()
    except Exception:
        host = str(base_url or "").lower()

    if host == "10086.cn" or host.endswith(".10086.cn"):
        return {
            "enable_moderation": False,
            "reasoning": {"enabled": False},
        }

    return {
        "thinking": {"type": "disabled"},
    }


class _FallbackChatInvokeCompletion:
    def __init__(self, *, completion: Any, usage: Any = None, raw_response: Any = None):
        self.completion = completion
        self.usage = usage
        self.raw_response = raw_response


class _StructuredBrowserUseLLMAdapter:
    """browser-use 统一结构化输出适配器。

    不再按模型名称分支。是否使用原生 JSON、是否本地解析 JSON、是否传
    response_format/extra_body 等，都由 BrowserUseConfig 的能力配置决定。
    """

    def __init__(
            self,
            *,
            base_llm: Any,
            model_name: str,
            base_url: str,
            api_key: str,
            provider_name: str = "openai-like",
            force_json_mode: bool = True,
            max_retries: int = 2,
            use_response_format: bool = False,
            structured_output_mode: str = "local_json",
            normalize_actions: bool = True,
    ) -> None:
        self._base_llm = base_llm
        self.model = model_name
        self.model_name = model_name
        self.provider = provider_name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._provider_name = provider_name
        self._force_json_mode = bool(force_json_mode)
        self._max_retries = max(1, int(max_retries or 1))
        self._use_response_format = bool(use_response_format)
        self._structured_output_mode = str(structured_output_mode or "local_json").strip().lower()
        self._normalize_actions = bool(normalize_actions)
        self._client: Any = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base_llm, name)

    def _request_extra_body(self) -> Dict[str, Any]:
        """Browser agent requests never run with model thinking enabled."""
        return _browser_agent_no_thinking_extra_body(self._base_url)

    async def _ainvoke_unstructured_no_thinking(self, messages: Any) -> Any:
        """Invoke non-structured browser LLM calls with the same mandatory switch."""
        client = self._get_async_client()
        payload_messages = self._massage_messages(self._normalize_messages(messages))
        response = await client.chat.completions.create(
            model=self.model_name,
            messages=payload_messages,
            extra_body=self._request_extra_body(),
        )
        content = self._extract_response_content(response)
        usage = self._build_usage_summary(response)
        return self._build_chat_invoke_completion(
            completion=content,
            usage=usage,
            raw_response=response,
        )

    async def ainvoke(self, messages: Any, output_format: Any = None, *args: Any, **kwargs: Any) -> Any:
        try:
            if output_format is None or not self._force_json_mode:
                return await self._ainvoke_unstructured_no_thinking(messages)
            return await self._ainvoke_with_json_mode(messages=messages, output_format=output_format)
        except ValueError as e:
            if "missing required field: action" in str(e):
                # 返回一个空的、符合 browser-use 预期的 completion
                dummy_completion = {"action": [{"wait": {}}], "evaluation_previous_goal": "", "memory": "",
                                    "next_goal": ""}
                return self._build_chat_invoke_completion(
                    completion=dummy_completion,
                    usage=None,
                    raw_response=None
                )
            raise

    async def _ainvoke_with_json_mode(self, *, messages: Any, output_format: Any) -> Any:
        mode = self._structured_output_mode
        if mode == "native_json":
            return await self._ainvoke_native_json(messages=messages, output_format=output_format)
        if mode == "auto":
            try:
                return await self._ainvoke_native_json(messages=messages, output_format=output_format)
            except Exception:
                return await self._ainvoke_local_json(messages=messages, output_format=output_format)
        return await self._ainvoke_local_json(messages=messages, output_format=output_format)

    async def _ainvoke_native_json(self, *, messages: Any, output_format: Any) -> Any:
        client = self._get_async_client()
        schema = self._model_schema(output_format)
        payload_messages = self._normalize_messages(messages)
        payload_messages = self._massage_messages(payload_messages)
        payload_messages.insert(
            0,
            {
                "role": "system",
                "content": (
                    "You are controlling a browser automation agent. "
                    "Return ONLY one valid JSON object. "
                    "Do not use markdown fences. Do not explain. "
                    "Do not output null for required fields. "
                    "The JSON must match this schema exactly:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}"
                ),
            },
        )

        last_error: Optional[Exception] = None
        for _attempt in range(1, self._max_retries + 1):
            try:
                request_kwargs: Dict[str, Any] = {
                    "model": self.model_name,
                    "messages": payload_messages,
                }
                if self._use_response_format:
                    request_kwargs["response_format"] = {"type": "json_object"}
                request_kwargs["extra_body"] = self._request_extra_body()
                response = await client.chat.completions.create(**request_kwargs)
                content = self._extract_response_content(response)
                if not content:
                    raise ValueError(f"{self._provider_name} returned empty content in native_json mode")
                data = self._loads_json_object(content)
                if self._normalize_actions:
                    data = self._normalize_browser_use_payload(data)
                completion = self._validate_output(output_format, data)
                usage = self._build_usage_summary(response)
                return self._build_chat_invoke_completion(
                    completion=completion,
                    usage=usage,
                    raw_response=response,
                )
            except Exception as exc:
                last_error = exc
                continue
        raise RuntimeError(
            f"{self._provider_name} native_json structured output failed after {self._max_retries} attempts: "
            f"{self._summarize_exception(last_error) if last_error else 'unknown error'}"
        )

    async def _ainvoke_local_json(self, *, messages: Any, output_format: Any) -> Any:
        """调用底层 ChatOpenAI，再在本地解析/校验 JSON。

        如果网关因页面视觉/OCR上下文返回 403，则自动去掉 image/screenshot
        类内容，并用 OpenAI-compatible client 直接请求文本版 messages 重试一次。
        """
        last_error: Optional[Exception] = None
        last_raw: Any = None
        tried_text_only = False

        for _attempt in range(1, self._max_retries + 1):
            try:
                dict_messages = self._massage_messages(self._normalize_messages(messages))
                return await self._ainvoke_dict_messages_json(
                    dict_messages=dict_messages,
                    output_format=output_format,
                )
            except Exception as exc:
                last_error = exc
                if (not tried_text_only) and self._looks_like_403_from_page_context(exc):
                    text_only = self._strip_visual_context_from_messages(messages)
                    if text_only:
                        tried_text_only = True
                        try:
                            return await self._ainvoke_dict_messages_json(
                                dict_messages=text_only,
                                output_format=output_format,
                            )
                        except Exception as fallback_exc:
                            last_error = fallback_exc
                continue

        raise RuntimeError(
            f"{self._provider_name} local_json structured output failed after {self._max_retries} attempts: "
            f"{self._summarize_exception(last_error) if last_error else 'unknown error'}"
        )

    def _extract_completion_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            try:
                return str(value["choices"][0]["message"].get("content") or "").strip()
            except Exception:
                pass
            for key in ("content", "text", "output_text"):
                if isinstance(value.get(key), str):
                    return value[key].strip()
        completion = getattr(value, "completion", None)
        if completion is not None and completion is not value:
            text = self._extract_completion_text(completion)
            if text:
                return text
        message = getattr(value, "message", None)
        if message is not None and message is not value:
            text = self._extract_completion_text(message)
            if text:
                return text
        for attr in ("content", "text", "output_text"):
            content = getattr(value, attr, None)
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: List[str] = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        parts.append(str(item.get("text") or item.get("content") or ""))
                    else:
                        part = getattr(item, "text", None) or getattr(item, "content", None)
                        if part:
                            parts.append(str(part))
                joined = "\n".join(p for p in parts if p).strip()
                if joined:
                    return joined
        return str(value).strip()

    def _summarize_exception(self, exc: Exception) -> str:
        raw = str(exc)
        low = raw.lower()
        if "error code: 403" in low or "'code': 403" in low or '"code": 403' in low:
            hints = []
            if "内容不合规" in raw:
                hints.append("内容不合规")
            if "risk_detected" in low:
                hints.append("risk_detected")
            if "ocrtext" in low:
                hints.append("包含 OCR/页面视觉文本")
            if "risklevel" in low:
                hints.append("包含 riskLevel")
            suffix = f"；摘要：{', '.join(hints)}" if hints else ""
            return f"模型网关返回 403，请求被拒绝{suffix}。原始响应过长，已隐藏。"
        if "\\u" in raw:
            with contextlib.suppress(Exception):
                raw = raw.encode("utf-8", errors="replace").decode("unicode_escape", errors="ignore")
        raw = " ".join(raw.split())
        return raw[:500] + ("..." if len(raw) > 500 else "")

    def _looks_like_403_from_page_context(self, exc: Exception) -> bool:
        raw = str(exc)
        low = raw.lower()
        return (
            ("error code: 403" in low or "'code': 403" in low or '"code": 403' in low)
            and (
                "ocrtext" in low
                or "risk_detected" in low
                or "risklevel" in low
                or "内容不合规" in raw
                or "safe" in low
            )
        )

    def _drop_risky_page_context_text(self, text: str) -> str:
        """Remove screenshot/OCR/risk metadata that some gateways falsely flag.

        browser-use may convert visual page state into ordinary text before the
        adapter sees it, so filtering only image objects is not enough. Keep the
        useful DOM/task text, drop known visual-risk markers, and cap total size.
        """
        if not text:
            return ""

        marker_patterns = (
            r"ocr\s*text",
            r"ocrtext",
            r"risk[_\s-]*detected",
            r"risk[_\s-]*level",
            r"screenshot",
            r"image[_\s-]*url",
            r"input[_\s-]*image",
            r"视觉文本",
            r"页面视觉",
        )
        marker_re = re.compile("|".join(marker_patterns), re.IGNORECASE)

        kept: list[str] = []
        skipping_jsonish_block = False
        for line in str(text).splitlines():
            stripped = line.strip()
            if marker_re.search(stripped):
                skipping_jsonish_block = stripped.endswith(":") or stripped.endswith("{") or stripped.endswith("[")
                continue
            if skipping_jsonish_block:
                if stripped.startswith(("{", "}", "[", "]", '"', "'")) or stripped.endswith((",", "}", "]")):
                    continue
                skipping_jsonish_block = False
            kept.append(line)
        cleaned = "\n".join(kept).strip()
        try:
            max_chars = int(os.environ.get("BROWSER_TEXT_CONTEXT_MAX_CHARS", "12000"))
        except Exception:
            max_chars = 12000
        if max_chars > 0 and len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars].rstrip() + "\n...[truncated page context]"
        return cleaned

    def _strip_visual_context_from_messages(self, messages: Any) -> list[dict[str, Any]]:
        stripped: list[dict[str, Any]] = []
        for msg in list(messages or []):
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content")
            else:
                role = getattr(msg, "role", None) or getattr(msg, "type", None) or "user"
                content = getattr(msg, "content", None)
            content_text = self._normalize_content_text_only(content)
            if content_text.strip():
                stripped.append({"role": role, "content": content_text})
        return stripped

    async def _ainvoke_dict_messages_json(self, *, dict_messages: list[dict[str, Any]], output_format: Any) -> Any:
        """Invoke the OpenAI-compatible endpoint with normalized dict messages.

        Used only as fallback when browser_use.ChatOpenAI rejects/blocks visual
        message content. Do not pass dict messages back to browser_use.ChatOpenAI,
        because it expects browser-use message objects and raises
        "Unknown message type: <class 'dict'>".
        """
        client = self._get_async_client()
        request_kwargs: Dict[str, Any] = {
            "model": self.model_name,
            "messages": dict_messages,
        }
        if self._use_response_format:
            request_kwargs["response_format"] = {"type": "json_object"}
        request_kwargs["extra_body"] = self._request_extra_body()
        response = await client.chat.completions.create(**request_kwargs)
        content = self._extract_response_content(response)
        if not content:
            raise ValueError(f"{self._provider_name} returned empty content in text-only fallback")
        data = self._loads_json_object(content)
        if self._normalize_actions:
            data = self._normalize_browser_use_payload(data)
        completion = self._validate_output(output_format, data)
        usage = self._build_usage_summary(response)
        return self._build_chat_invoke_completion(
            completion=completion,
            usage=usage,
            raw_response=response,
        )

    def _normalize_content_text_only(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return self._drop_risky_page_context_text(content)
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    typ = str(item.get("type") or "").lower()
                    if typ in {"image", "image_url", "input_image", "screenshot"}:
                        continue
                    if "text" in item:
                        parts.append(str(item.get("text") or ""))
                    elif typ == "text":
                        parts.append(str(item.get("content") or ""))
                else:
                    txt = getattr(item, "text", None)
                    if txt is not None:
                        parts.append(str(txt))
            return self._drop_risky_page_context_text("\n".join(p for p in parts if p))
        return self._drop_risky_page_context_text(str(content))

    def _get_async_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI
            kwargs: Dict[str, Any] = {"api_key": self._api_key, "base_url": self._base_url}
            raw_timeout = os.environ.get("BROWSER_USE_LLM_TIMEOUT") or os.environ.get("OPENAI_REQUEST_TIMEOUT")
            if raw_timeout:
                with contextlib.suppress(Exception):
                    kwargs["timeout"] = float(raw_timeout)
            self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _massage_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        fixed = list(messages)
        first_non_system = next((i for i, m in enumerate(fixed) if m.get("role") != "system"), None)
        if first_non_system is not None and fixed[first_non_system].get("role") == "assistant":
            fixed[first_non_system]["role"] = "user"
        if self.provider in {"glm", "deepseek"}:
            fixed.append(
                {
                    "role": "user",
                    "content": (
                        "Remember: output ONLY one valid JSON object. "
                        "Do not use null for required fields. "
                        "Use field name action, not actions. "
                        "Do not wrap in markdown."
                    ),
                }
            )
        return fixed

    def _normalize_messages(self, messages: Any) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for message in list(messages or []):
            if isinstance(message, dict):
                role = message.get("role", "user")
                content = self._normalize_content(message.get("content"))
            else:
                role = getattr(message, "role", None) or getattr(message, "type", None) or "user"
                content = self._normalize_content(getattr(message, "content", None))
            normalized.append({"role": role, "content": content or ""})
        return normalized

    def _normalize_content(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                    elif "text" in item:
                        parts.append(str(item.get("text", "")))
                else:
                    text = getattr(item, "text", None)
                    if text is not None:
                        parts.append(str(text))
            return "\n".join(part for part in parts if part)
        return str(content)

    def _extract_response_content(self, response: Any) -> str:
        try:
            message = response.choices[0].message
        except Exception as exc:
            raise ValueError(f"Unexpected {self._provider_name} response shape: {response!r}") from exc
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(p for p in parts if p).strip()
        return str(content or "").strip()

    def _loads_json_object(self, text: str) -> Dict[str, Any]:
        candidate = text.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            if len(lines) >= 3:
                candidate = "\n".join(lines[1:-1]).strip()
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start < 0 or end < 0 or end <= start:
                raise
            loaded = json.loads(candidate[start: end + 1])
        if not isinstance(loaded, dict):
            raise ValueError(f"Expected JSON object, got: {type(loaded).__name__}")
        return loaded

    def _normalize_browser_use_action(self, action: Any) -> Any:
        """宽松兼容 Qwen/非严格模型输出的 browser-use 0.9.x 动作格式。

        目标：不要要求模型一次性完全遵守 Pydantic schema；先把常见同义动作名、
        常见字段名、扁平写法、本应是 dict 却写成字符串/数字的写法，统一归一化，
        再交给 browser-use 自己做最终校验。
        """
        if not isinstance(action, dict):
            return action

        fixed = dict(action)

        def _coerce_index(value: Any) -> Any:
            if isinstance(value, str) and value.strip().isdigit():
                return int(value.strip())
            return value

        def _take_first(d: Dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
            for k in keys:
                if k in d and d[k] is not None:
                    return d[k]
            return default

        def _normalize_element_payload(payload: Any, *, default_text: Any = None) -> Any:
            """把 element/element_id/selector 等别名尽量转成 browser-use 0.9.x 常用的 index/text。"""
            if isinstance(payload, (int, float)) or (isinstance(payload, str) and payload.strip().isdigit()):
                return {"index": _coerce_index(payload)}
            if not isinstance(payload, dict):
                if default_text is not None:
                    return {"text": str(default_text)}
                return payload

            item = dict(payload)
            if "index" not in item:
                for alias in (
                    "element", "element_index", "element_id", "node", "node_id",
                    "target", "target_index", "idx", "id",
                ):
                    if alias in item:
                        item["index"] = _coerce_index(item.pop(alias))
                        break
            else:
                item["index"] = _coerce_index(item.get("index"))

            if "text" not in item:
                for alias in ("value", "content", "query", "keyword", "keys"):
                    if alias in item:
                        item["text"] = item.pop(alias)
                        break
            return item

        action_aliases = {
            "switch_tab": "switch",
            "switch_to_tab": "switch",
            "select_tab": "switch",
            "change_tab": "switch",
            "activate_tab": "switch",
            "tab": "switch",
            "type": "input",
            "type_text": "input",
            "fill": "input",
            "fill_input": "input",
            "enter_text": "input",
            "input_text": "input",
            "click_element": "click",
            "press": "send_keys",
            "press_key": "send_keys",
            "keyboard": "send_keys",
            "send_key": "send_keys",
            "keypress": "send_keys",
            "key_press": "send_keys",
            "key_down": "send_keys",
            "keydown": "send_keys",
            "keyboard_press": "send_keys",
            "press_enter": "send_keys",
            "enter": "send_keys",
            "submit": "send_keys",
            "submit_form": "send_keys",
            "go_back": "go_back",
            "back": "go_back",
            "finish": "done",
            "final": "done",
            "final_answer": "done",
            "answer": "done",
        }
        for alias, canonical in action_aliases.items():
            if canonical not in fixed and alias in fixed:
                fixed[canonical] = fixed.pop(alias)

        def _coerce_scroll_pages(payload: Any) -> float:
            """Convert model-emitted scroll pixels/pages into a bounded browser-use pages value."""
            raw: Any = 1.0
            if isinstance(payload, dict):
                raw = payload.get("pages", payload.get("amount", payload.get("distance", 1.0)))
            elif payload not in (None, ""):
                raw = payload
            try:
                value = abs(float(raw))
            except Exception:
                value = 1.0
            if value > 20:
                value = value / 800.0
            return max(0.5, min(value, 5.0))

        if "scroll_down" in fixed and "scroll" not in fixed:
            payload = fixed.pop("scroll_down")
            fixed["scroll"] = {"down": True, "pages": _coerce_scroll_pages(payload)}
        if "scroll_up" in fixed and "scroll" not in fixed:
            payload = fixed.pop("scroll_up")
            fixed["scroll"] = {"down": False, "pages": _coerce_scroll_pages(payload)}
        if "scroll_to_top" in fixed and "scroll" not in fixed:
            fixed.pop("scroll_to_top", None)
            fixed["scroll"] = {"down": False, "pages": 5.0}
        if "scroll_to_bottom" in fixed and "scroll" not in fixed:
            fixed.pop("scroll_to_bottom", None)
            fixed["scroll"] = {"down": True, "pages": 5.0}

        supported_actions = {
            "done", "search", "navigate", "go_back", "wait", "click", "input", "upload_file",
            "switch", "close", "scroll", "send_keys", "find_text", "dropdown_options",
            "select_dropdown", "write_file", "replace_file", "read_file", "evaluate",
        }
        observe_only_actions = ("extract", "extract_content", "screenshot", "observe", "inspect")
        unsupported_observe = next((name for name in observe_only_actions if name in fixed), None)
        if unsupported_observe is not None:
            fixed.pop(unsupported_observe, None)
            if not any(name in fixed for name in supported_actions):
                fixed["wait"] = {}

        if not any(k in fixed for k in (
            "done", "search", "navigate", "go_back", "wait", "click", "input", "upload_file",
            "switch", "close", "scroll", "send_keys", "find_text",
            "dropdown_options", "select_dropdown", "write_file", "replace_file", "read_file", "evaluate",
        )):
            flat_text = _take_first(fixed, ("text", "value", "content", "query", "keyword"))
            flat_index = _take_first(fixed, ("index", "element", "element_index", "element_id", "idx", "id"))
            if flat_text is not None and flat_index is not None:
                fixed = {"input": {"text": flat_text, "index": _coerce_index(flat_index)}}

        # -------- 各动作参数归一化 --------
        if "switch" in fixed:
            sw = fixed["switch"]
            if isinstance(sw, dict):
                sw = dict(sw)
                if "tab_id" not in sw:
                    for alias in ("tab", "id", "target", "target_id", "page_id"):
                        if alias in sw:
                            sw["tab_id"] = sw.pop(alias)
                            break
                fixed["switch"] = sw
            else:
                fixed["switch"] = {"tab_id": str(sw)}

        if "wait" in fixed:
            fixed["wait"] = {}

        if "input" in fixed:
            if isinstance(fixed["input"], dict):
                fixed["input"] = _normalize_element_payload(fixed["input"])
            else:
                text = fixed.pop("input")
                index = _take_first(fixed, ("index", "element", "element_index", "element_id", "idx", "id"))
                fixed["input"] = {"text": str(text)}
                if index is not None:
                    fixed["input"]["index"] = _coerce_index(index)
                for k in ("index", "element", "element_index", "element_id", "idx", "id"):
                    fixed.pop(k, None)

        if "click" in fixed:
            fixed["click"] = _normalize_element_payload(fixed["click"])

        if "send_keys" in fixed:
            if not isinstance(fixed["send_keys"], dict):
                raw_keys = fixed["send_keys"]
                if isinstance(raw_keys, (list, tuple)):
                    raw_keys = "+".join(str(x) for x in raw_keys if x is not None)
                fixed["send_keys"] = {"keys": str(raw_keys)}
            else:
                sk = dict(fixed["send_keys"])
                if "keys" not in sk:
                    for alias in ("key", "text", "value", "content", "button"):
                        if alias in sk:
                            sk["keys"] = sk.pop(alias)
                            break
                raw_keys = sk.get("keys")
                if isinstance(raw_keys, (list, tuple)):
                    sk["keys"] = "+".join(str(x) for x in raw_keys if x is not None)
                elif raw_keys is None:
                    sk["keys"] = "Enter"
                else:
                    sk["keys"] = str(raw_keys)
                key_aliases = {
                    "Return": "Enter",
                    "RETURN": "Enter",
                    "Enter": "Enter",
                    "ENTER": "Enter",
                    "NumpadEnter": "Enter",
                    "Esc": "Escape",
                    "ESC": "Escape",
                    "Escape": "Escape",
                }
                sk["keys"] = key_aliases.get(sk["keys"], sk["keys"])
                fixed["send_keys"] = sk

        for key in (
            "scroll", "find_text", "dropdown_options", "select_dropdown",
            "upload_file", "evaluate",
        ):
            if key in fixed and isinstance(fixed[key], dict):
                fixed[key] = _normalize_element_payload(fixed[key])

        if "navigate" in fixed and isinstance(fixed["navigate"], str):
            fixed["navigate"] = {"url": fixed["navigate"]}
        if "search" in fixed and isinstance(fixed["search"], str):
            fixed["search"] = {"query": fixed["search"]}
        if "done" in fixed:
            if isinstance(fixed["done"], str):
                fixed["done"] = {"text": fixed["done"], "success": True}
            elif isinstance(fixed["done"], dict):
                done = dict(fixed["done"])
                if "text" not in done:
                    for alias in ("answer", "message", "content", "result"):
                        if alias in done:
                            done["text"] = done.pop(alias)
                            break
                done.setdefault("success", True)
                fixed["done"] = done

        return fixed

    def _normalize_browser_use_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(data)
        current_state = normalized.get("current_state")
        if isinstance(current_state, dict):
            for key in ("evaluation_previous_goal", "memory", "next_goal"):
                if key not in normalized and key in current_state:
                    normalized[key] = current_state[key]
        if "action" not in normalized and "actions" in normalized:
            normalized["action"] = normalized["actions"]
        if isinstance(normalized.get("action"), dict):
            normalized["action"] = [normalized["action"]]
        if not normalized.get("action") and isinstance(normalized.get("tool_calls"), list):
            actions = []
            for tc in normalized["tool_calls"]:
                if not isinstance(tc, dict):
                    continue
                fn = tc.get("function") or {}
                name = fn.get("name")
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if name and isinstance(args, dict):
                    actions.append({name: args})
            if actions:
                normalized["action"] = actions
        for key in ("evaluation_previous_goal", "memory", "next_goal"):
            value = normalized.get(key)
            if value is None:
                normalized[key] = ""
            elif not isinstance(value, str):
                normalized[key] = str(value)
        action = normalized.get("action")
        if action is None:
            if "done" in normalized:
                action = [{"done": normalized["done"]}]
            elif "final_result" in normalized:
                action = [{"done": {"text": normalized["final_result"], "success": True}}]
            elif "text" in normalized:
                action = [{"done": {"text": normalized["text"], "success": True}}]
            else:
                # 最后尝试：如果什么都没有，构造一个 wait 动作避免崩溃
                action = [{"wait": {}}]
            normalized["action"] = action
        if isinstance(action, dict):
            normalized["action"] = [action]
            action = normalized["action"]
        elif isinstance(action, list):
            flattened: list[Any] = []
            pending = list(action)
            while pending:
                item = pending.pop(0)
                if isinstance(item, list):
                    pending = list(item) + pending
                elif isinstance(item, dict) and item:
                    flattened.append(item)
            normalized["action"] = flattened or [{"wait": {}}]
            action = normalized["action"]
        elif not isinstance(action, list) or len(action) == 0:
            raise ValueError(f"{self._provider_name} output invalid action field: {action!r}")
        normalized["action"] = [self._normalize_browser_use_action(item) for item in normalized["action"]]
        return normalized

    def _model_schema(self, output_format: Any) -> Dict[str, Any]:
        if hasattr(output_format, "model_json_schema"):
            return output_format.model_json_schema()
        if hasattr(output_format, "schema"):
            return output_format.schema()
        return {"type": "object"}

    def _validate_output(self, output_format: Any, data: Dict[str, Any]) -> Any:
        if hasattr(output_format, "model_validate"):
            return output_format.model_validate(data)
        if hasattr(output_format, "parse_obj"):
            return output_format.parse_obj(data)
        return output_format(**data)

    def _build_chat_invoke_completion(self, *, completion: Any, usage: Any, raw_response: Any) -> Any:
        completion_cls = self._resolve_chat_invoke_completion_cls()
        try:
            sig = inspect.signature(completion_cls)
            kwargs: Dict[str, Any] = {}
            if "completion" in sig.parameters:
                kwargs["completion"] = completion
            if "usage" in sig.parameters:
                kwargs["usage"] = usage
            if "raw_response" in sig.parameters:
                kwargs["raw_response"] = raw_response
            if kwargs:
                return completion_cls(**kwargs)
        except Exception:
            pass
        try:
            return completion_cls(completion=completion, usage=usage)
        except Exception:
            return _FallbackChatInvokeCompletion(completion=completion, usage=usage, raw_response=raw_response)

    def _resolve_chat_invoke_completion_cls(self) -> Any:
        try:
            from browser_use.llm.views import ChatInvokeCompletion
            return ChatInvokeCompletion
        except Exception:
            return _FallbackChatInvokeCompletion

    def _build_usage_summary(self, response: Any) -> Any:
        raw_usage = getattr(response, "usage", None)
        usage_data = self._usage_to_dict(raw_usage)
        usage_cls = self._resolve_chat_invoke_usage_cls()
        payload: Dict[str, Any] = {
            "prompt_tokens": int(self._pick_usage_value("prompt_tokens", usage_data) or 0),
            "prompt_cached_tokens": self._coerce_optional_int(
                self._pick_usage_value("prompt_cached_tokens", usage_data)),
            "prompt_cache_creation_tokens": self._coerce_optional_int(
                self._pick_usage_value("prompt_cache_creation_tokens", usage_data)),
            "prompt_image_tokens": self._coerce_optional_int(self._pick_usage_value("prompt_image_tokens", usage_data)),
            "completion_tokens": int(self._pick_usage_value("completion_tokens", usage_data) or 0),
            "total_tokens": int(self._pick_usage_value("total_tokens", usage_data) or 0),
        }
        if usage_cls is None:
            return payload
        try:
            return usage_cls(**payload)
        except Exception:
            return payload

    def _resolve_chat_invoke_usage_cls(self) -> Any:
        try:
            from browser_use.llm.views import ChatInvokeUsage
            return ChatInvokeUsage
        except Exception:
            return None

    def _usage_to_dict(self, raw_usage: Any) -> Dict[str, Any]:
        if raw_usage is None:
            return {}
        if isinstance(raw_usage, dict):
            return {str(k): v for k, v in raw_usage.items()}
        if hasattr(raw_usage, "model_dump"):
            try:
                dumped = raw_usage.model_dump()
                if isinstance(dumped, dict):
                    return {str(k): v for k, v in dumped.items()}
            except Exception:
                pass
        if hasattr(raw_usage, "dict"):
            try:
                dumped = raw_usage.dict()
                if isinstance(dumped, dict):
                    return {str(k): v for k, v in dumped.items()}
            except Exception:
                pass
        data: Dict[str, Any] = {}
        for name in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "cached_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
        ):
            value = getattr(raw_usage, name, None)
            if value is not None:
                data[name] = value
        return data

    def _pick_usage_value(self, field_name: str, usage_data: Dict[str, Any]) -> Any:
        if field_name in usage_data:
            return usage_data[field_name]
        aliases = {
            "input_tokens": ["prompt_tokens"],
            "output_tokens": ["completion_tokens"],
            "prompt_tokens": ["input_tokens"],
            "completion_tokens": ["output_tokens"],
            "prompt_cached_tokens": ["cached_tokens", "cache_read_input_tokens", "prompt_cache_hit_tokens"],
            "prompt_cache_creation_tokens": ["cache_creation_input_tokens", "prompt_cache_miss_tokens"],
            "prompt_image_tokens": ["image_tokens"],
        }
        for alt in aliases.get(field_name, []):
            if alt in usage_data:
                return usage_data[alt]
        if field_name == "total_tokens":
            prompt = usage_data.get("prompt_tokens", usage_data.get("input_tokens", 0)) or 0
            completion = usage_data.get("completion_tokens", usage_data.get("output_tokens", 0)) or 0
            reasoning = usage_data.get("reasoning_tokens", 0) or 0
            total = usage_data.get("total_tokens")
            return total if total is not None else prompt + completion + reasoning
        return None

    def _coerce_optional_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None


class BrowserUseConfig(ToolkitConfigBase):
    target: Literal[
        "core.tools.browser_tool.browser_toolkit.BrowserUseToolkit"] = "core.tools.browser_tool.browser_toolkit.BrowserUseToolkit"  # type: ignore
    agent_type: str = "browser_use"
    model: Optional[List[str]] = None
    inner_model: Optional[List[str]] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    toolkit_name: str = "browser_use"
    toolkit_instructions: str = "用于调用 browser-use 执行网页浏览、搜索、点击、表单填写与页面信息提取。"
    llm: Optional[Any] = None
    llm_factory: Optional[Callable[[], Any]] = None
    browser_factory: Optional[Callable[[], Any]] = None
    agent_factory: Optional[Callable[..., Any]] = None
    register_task_tools: bool = False
    prefer_direct_runner: bool = True

    cdp_url: Optional[str] = None
    headless: bool = False
    keep_alive: bool = False
    storage_state: Optional[str] = None
    profile_directory: Optional[str] = None
    user_data_dir: Optional[str] = None
    allowed_domains: Optional[List[str]] = None
    prohibited_domains: Optional[List[str]] = None
    executable_path: Optional[str] = None
    channel: Optional[str] = None
    proxy: Optional[str] = None
    viewport: Optional[Dict[str, int]] = None
    window_size: Optional[Dict[str, int]] = None
    window_position: Optional[Dict[str, int]] = None
    no_viewport: Optional[bool] = None
    minimum_wait_page_load_time: Optional[float] = 1.0
    wait_for_network_idle_page_load_time: Optional[float] = 1.0
    wait_between_actions: Optional[float] = 0.5
    trace_dir: Optional[str] = None
    record_video_dir: Optional[str] = None
    record_har_path: Optional[str] = None
    browser_kwargs: Dict[str, Any] = {}

    max_steps: int = 40
    max_actions_per_step: Optional[int] = 3
    max_failures: Optional[int] = 4
    use_vision: Optional[bool] = False
    vision_detail_level: Optional[str] = None
    flash_mode: Optional[bool] = None
    use_thinking: Optional[bool] = False
    step_timeout: Optional[int] = None
    llm_timeout: Optional[int] = None
    directly_open_url: Optional[bool] = None
    final_response_after_failure: Optional[bool] = None
    save_conversation_path: Optional[str] = None
    available_file_paths: Optional[List[str]] = None
    agent_file_system_dir: Optional[str] = None
    sensitive_data: Optional[Dict[str, Any]] = None
    extend_system_message: Optional[str] = None
    override_system_message: Optional[str] = None
    initial_actions: Optional[List[Dict[str, Any]]] = None
    generate_gif: Optional[bool] = None
    calculate_cost: Optional[bool] = None
    agent_kwargs: Dict[str, Any] = {}
    emit_step_summary: bool = True
    emit_step_text: bool = True
    retain_last_completed_tasks: int = 20
    structured_force_json_mode: bool = True
    structured_output_mode: Literal["local_json", "native_json", "auto", "off"] = "local_json"
    structured_use_response_format: bool = False
    structured_normalize_actions: bool = True
    structured_max_retries: int = 1

    @staticmethod
    def _secret_to_str(value: Any) -> str:
        if value is None:
            return ""
        get_secret_value = getattr(value, "get_secret_value", None)
        if callable(get_secret_value):
            try:
                return str(get_secret_value()).strip()
            except Exception:
                pass
        return str(value).strip()

    def _resolve_outer_model_name(self) -> str:
        if self.model:
            for name in self.model:
                if name and str(name).strip():
                    return str(name).strip()
        return ""

    def _resolve_inner_model_name(self) -> str:
        if self.inner_model:
            for name in self.inner_model:
                if name and str(name).strip():
                    return str(name).strip()
        return self._resolve_outer_model_name()

    def _resolve_model_name(self) -> str:
        return self._resolve_inner_model_name()

    def _resolve_switch_model_name(self) -> str:
        return self._resolve_inner_model_name()


    def _resolve_provider_name(self, model_name: Optional[str] = None) -> str:
        """从模型 ID 推导 provider 名称，用于 browser-use 日志展示。

        例如：
        - moonshotai/kimi-k2.5-thinking -> moonshotai
        - openai/gpt-4.1 -> openai
        - kimi-k2-5-thinking -> kimi-k2-5-thinking

        不再需要在 YAML 里手动写 structured_provider_name。
        """
        name = str(model_name or self._resolve_model_name() or "").strip()
        if not name:
            return "unknown"
        if "/" in name:
            head = name.split("/", 1)[0].strip()
            return head or name
        return name

    def _resolve_base_url(self) -> str:
        url = self._secret_to_str(getattr(self, "base_url", None)).rstrip("/")
        if url.endswith("/chat/completions"):
            return url[: -len("/chat/completions")]
        return url

    def _resolve_api_key(self) -> str:
        return self._secret_to_str(getattr(self, "api_key", None))

    def build_outer_model(self) -> OpenAILike:
        return OpenAILike(
            id=self._resolve_outer_model_name(),
            base_url=self._resolve_base_url(),
            api_key=self._resolve_api_key(),
            request_params={"extra_body": _browser_agent_no_thinking_extra_body(self._resolve_base_url())},
        )

    def _build_browser_use_chatopenai(self, *, model_name: str, base_url: str, api_key: str) -> Any:
        from browser_use import ChatOpenAI

        kwargs: Dict[str, Any] = {"model": model_name, "base_url": base_url, "api_key": api_key}
        raw_timeout = os.environ.get("BROWSER_USE_LLM_TIMEOUT") or os.environ.get("OPENAI_REQUEST_TIMEOUT")
        if raw_timeout:
            with contextlib.suppress(Exception):
                kwargs["timeout"] = float(raw_timeout)
        try:
            return ChatOpenAI(**kwargs)
        except TypeError:
            # Some browser-use/langchain versions do not expose a timeout kwarg.
            kwargs.pop("timeout", None)
            return ChatOpenAI(**kwargs)

    def _patch_browser_use_attrs(self, llm: Any, *, provider: str) -> Any:
        for attr, value in {
            "provider": provider,
            "model": getattr(llm, "model", None) or self._resolve_model_name(),
            "model_name": getattr(llm, "model_name", None) or self._resolve_model_name(),
        }.items():
            try:
                setattr(llm, attr, value)
            except Exception:
                pass
        return llm

    def get_model_profile(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        mode = str(getattr(self, "structured_output_mode", "local_json") or "local_json").strip().lower()
        needs_structured_adapter = bool(getattr(self, "structured_force_json_mode", True)) and mode not in {"off", "none", "false"}
        provider_name = self._resolve_provider_name(model_name)
        return {
            "needs_structured_adapter": needs_structured_adapter,
            "use_vision": self.use_vision,
            "use_thinking": self.use_thinking,
            "max_actions_per_step": self.max_actions_per_step,
            "flash_mode": self.flash_mode,
            "final_response_after_failure": self.final_response_after_failure,
            "provider_name": provider_name,
            "structured_output_mode": mode,
            "structured_use_response_format": bool(getattr(self, "structured_use_response_format", False)),
            "structured_normalize_actions": bool(getattr(self, "structured_normalize_actions", True)),
        }

    def build_inner_llm(self) -> Any:
        if self.llm is not None:
            return self.llm
        if self.llm_factory is not None:
            return self.llm_factory()

        model_name = self._resolve_model_name()
        base_url = self._resolve_base_url()
        api_key = self._resolve_api_key()
        profile = self.get_model_profile(model_name)

        llm = self._build_browser_use_chatopenai(
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
        )
        llm = self._patch_browser_use_attrs(llm, provider=profile["provider_name"])
        llm = _StructuredBrowserUseLLMAdapter(
            base_llm=llm,
            model_name=model_name,
            base_url=base_url,
            api_key=api_key,
            provider_name=profile["provider_name"],
            force_json_mode=bool(getattr(self, "structured_force_json_mode", True)),
            max_retries=int(getattr(self, "structured_max_retries", 2) or 2),
            use_response_format=bool(profile.get("structured_use_response_format", False)),
            structured_output_mode=str(profile.get("structured_output_mode", "local_json")),
            normalize_actions=bool(profile.get("structured_normalize_actions", True)),
        )
        return self._patch_browser_use_attrs(llm, provider=profile["provider_name"])

    def validate(self, **kwargs) -> None:
        missing = []
        if not self._resolve_model_name():
            missing.append("inner_model/model")
        if not self._resolve_base_url():
            missing.append("base_url")
        if not self._resolve_api_key():
            missing.append("api_key")
        if missing:
            raise ValueError("BrowserUseConfig 缺少关键运行参数: " + ", ".join(missing))
        return
