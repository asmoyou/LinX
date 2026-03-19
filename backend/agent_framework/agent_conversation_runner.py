"""Shared agent initialization helpers for chat-style execution."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from uuid import UUID

from agent_framework.base_agent import AgentConfig, BaseAgent
from llm_providers.custom_openai_provider import CustomOpenAIChat
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

_REASONING_TITLE_MARKERS = (
    "thinking process",
    "reasoning process",
    "analyze the request",
    "role:",
    "system:",
    "assistant:",
    "user:",
    "good at naming conversations",
    "good at naming dialogue",
    "good at naming chats",
    "conversation naming assistant",
    "擅长给对话命名的助手",
    "对话命名助手",
    "output format",
    "single line json",
    "{\"title\"",
    "`{\"title\"",
    "json format",
    "task:",
    "task：",
    "generate a concise and accurate conversation title",
    "conversation title based",
    "generate a title",
    "title based on",
    "input:",
    "output:",
    "user asking",
    "assistant reply",
    "assistant response",
    "step 1",
    "step one",
    "i need to",
    "let me",
    "首先",
    "第一步",
    "分析请求",
    "生成一个简洁准确的会话标题",
    "会话标题",
)

_RAW_TITLE_PROMPT_ECHO_MARKERS = (
    "output format",
    "single line json",
    "task:",
    "task：",
    "input:",
    "output:",
    "role:",
    "system:",
    "assistant:",
    "user:",
    "good at naming conversations",
    "conversation naming assistant",
    "擅长给对话命名的助手",
    "标题内容",
    "title content",
)


async def initialize_chat_agent(
    *,
    agent_info,
    owner_user_id: UUID,
    max_iterations: int = 20,
) -> BaseAgent:
    """Create and initialize a BaseAgent for chat execution."""
    config = AgentConfig(
        agent_id=agent_info.agent_id,
        name=agent_info.name,
        agent_type=agent_info.agent_type,
        owner_user_id=owner_user_id,
        capabilities=agent_info.capabilities or [],
        access_level=agent_info.access_level or "private",
        allowed_knowledge=agent_info.allowed_knowledge or [],
        llm_model=agent_info.llm_model or "llama3.2:latest",
        temperature=agent_info.temperature or 0.7,
        max_iterations=max_iterations,
        system_prompt=agent_info.system_prompt,
    )
    agent = BaseAgent(config)
    agent.llm = _build_llm_for_agent(agent_info)
    await agent.initialize()
    return agent


def _build_llm_for_agent(
    agent_info,
    *,
    streaming: bool = True,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> CustomOpenAIChat:
    from database.connection import get_db_session
    from llm_providers.db_manager import ProviderDBManager

    provider_name = agent_info.llm_provider or "ollama"
    model_name = agent_info.llm_model or "llama3.2:latest"
    resolved_temperature = temperature if temperature is not None else (agent_info.temperature or 0.7)
    resolved_max_tokens = max_tokens if max_tokens is not None else agent_info.max_tokens

    with get_db_session() as db:
        db_manager = ProviderDBManager(db)
        db_provider = db_manager.get_provider(provider_name)
        if not db_provider or not db_provider.enabled:
            raise ValueError(f"Provider '{provider_name}' not found or disabled")

        if db_provider.protocol == "openai_compatible":
            api_key: Optional[str] = None
            if db_provider.api_key_encrypted:
                api_key = db_manager._decrypt_api_key(db_provider.api_key_encrypted)
            return CustomOpenAIChat(
                base_url=db_provider.base_url,
                model=model_name,
                temperature=resolved_temperature,
                api_key=api_key,
                timeout=db_provider.timeout,
                max_retries=db_provider.max_retries,
                max_tokens=resolved_max_tokens,
                streaming=streaming,
            )

        if db_provider.protocol == "ollama":
            return CustomOpenAIChat(
                base_url=db_provider.base_url,
                model=model_name,
                temperature=resolved_temperature,
                max_tokens=resolved_max_tokens,
                api_key=None,
                streaming=streaming,
            )

    raise ValueError(f"Could not create LLM for provider: {provider_name}")


def _sanitize_generated_title(raw_title: object, max_chars: int = 60) -> str:
    raw_text = str(raw_title or "").strip()
    if not raw_text:
        return ""

    json_match = re.search(r'"title"\s*:\s*"([^"]+)"', raw_text, flags=re.IGNORECASE)
    if json_match:
        raw_text = json_match.group(1).strip()

    inline_match = re.search(r"(?:标题|title)\s*[:：-]\s*(.+)", raw_text, flags=re.IGNORECASE)
    if inline_match:
        raw_text = inline_match.group(1).strip()

    lines = []
    for line in raw_text.splitlines():
        normalized = " ".join(line.split()).strip()
        normalized = re.sub(r"^[#>*\-\d.\s]+", "", normalized)
        normalized = re.sub(r"^(?:标题|title)\s*[:：-]\s*", "", normalized, flags=re.IGNORECASE)
        normalized = normalized.strip(' \'"`“”‘’#*_[](){}<>-:：;；,.!?！？。')
        if normalized:
            lines.append(normalized)

    candidates = [line for line in lines if not _looks_like_reasoning_title(line)]
    title = candidates[0] if candidates else ""
    if len(title) > max_chars:
        title = title[:max_chars].rstrip(' \'"`“”‘’#*_[](){}<>-:：;；,.!?！？。')
    return title


def _looks_like_reasoning_title(value: object) -> bool:
    normalized = " ".join(str(value or "").split()).strip().lower()
    if not normalized:
        return False
    if "{" in normalized or "}" in normalized or "`" in normalized:
        return True
    if re.match(r"^(role|system|assistant|user)\s*[:：]", normalized):
        return True
    if any(marker in normalized for marker in _REASONING_TITLE_MARKERS):
        return True
    if normalized.count("**") >= 2:
        return True
    if re.match(r"^\d+[.)]\s+", normalized):
        return True
    return False


def _raw_title_candidate_is_prompt_echo(value: object) -> bool:
    normalized = " ".join(str(value or "").split()).strip().lower()
    if not normalized:
        return False
    if re.match(r"^(role|system|assistant|user)\s*[:：]", normalized):
        return True
    return any(marker in normalized for marker in _RAW_TITLE_PROMPT_ECHO_MARKERS)


def _trim_title(text: str, max_chars: int) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _fallback_title_from_user_message(user_message: str) -> Optional[str]:
    text = " ".join(str(user_message or "").split()).strip()
    if not text or text == "[Attached files]":
        return None

    if re.search(r"[\u4e00-\u9fff]", text):
        simplified = re.sub(r"^(你好|您好|请问|麻烦|帮我|可以|能不能|我想知道|我想了解)[，,\s]*", "", text)
        if simplified.startswith("怎么"):
            simplified = f"如何{simplified[2:]}"
        elif simplified.startswith("如何"):
            simplified = simplified
        return _trim_title(simplified, 18)

    simplified = re.sub(
        r"^(please\s+|can you\s+|could you\s+|would you\s+|i want to\s+|help me\s+)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    simplified = re.sub(r"^how to\s+", "", simplified, flags=re.IGNORECASE)
    simplified = re.sub(r"^how do i\s+", "", simplified, flags=re.IGNORECASE)
    simplified = simplified.strip(" ?!.,:;")
    if not simplified:
        return None
    simplified = simplified[:1].upper() + simplified[1:]
    return _trim_title(simplified, 36)


def _detect_title_language_hint(user_message: str) -> str:
    text = str(user_message or "")
    if re.search(r"[\u4e00-\u9fff]", text):
        return "标题语言必须使用中文。"
    if re.search(r"[ぁ-んァ-ン]", text):
        return "タイトルの言語は日本語にしてください。"
    if re.search(r"[가-힣]", text):
        return "제목 언어는 한국어로 작성하세요."
    return "The title must use the same primary language as the user's message."


async def generate_conversation_title(
    *,
    agent_info,
    user_message: str,
    assistant_message: str,
) -> Optional[str]:
    """Generate a concise conversation title with the agent's own configured model."""
    llm = _build_llm_for_agent(
        agent_info,
        streaming=False,
        temperature=0.2,
        max_tokens=48,
    )
    prompt = (
        "请基于下面这组对话，生成一个简洁准确的会话标题。\n"
        "你只能输出标题文本本身，只能一行。\n"
        "不要输出 JSON、markdown、解释、角色说明，也不要复述任务。\n"
        "不要输出 Input、Output、Task、Role、System、Assistant、User 等前缀。\n"
        "标题尽量控制在 8 到 18 个汉字，必要时可使用简短英文。\n"
        "不要出现“用户”“助手”“对话”等前缀。\n\n"
        f"{_detect_title_language_hint(user_message)}\n\n"
        f"用户首条消息：\n{user_message.strip() or '（无文本，仅附件）'}\n\n"
        f"助手首轮回复：\n{assistant_message.strip() or '（空）'}"
    )
    response = await asyncio.to_thread(
        llm.invoke,
        [
            SystemMessage(content="你只返回标题文本本身，不要返回提示词、角色说明、JSON 或解释。"),
            HumanMessage(content=prompt),
        ],
    )
    additional_kwargs = getattr(response, "additional_kwargs", {}) or {}
    raw_candidates = [
        additional_kwargs.get("final_content"),
        getattr(response, "content", response),
        additional_kwargs.get("reasoning_content"),
    ]
    for raw_candidate in raw_candidates:
        if _raw_title_candidate_is_prompt_echo(raw_candidate):
            logger.warning("Rejected conversation title candidate: %s", str(raw_candidate)[:200])
            continue
        title = _sanitize_generated_title(raw_candidate)
        if title and not _looks_like_reasoning_title(title):
            logger.info("Generated conversation title: %s", title)
            return title
        if raw_candidate:
            logger.warning("Rejected conversation title candidate: %s", str(raw_candidate)[:200])
    return _fallback_title_from_user_message(user_message)
