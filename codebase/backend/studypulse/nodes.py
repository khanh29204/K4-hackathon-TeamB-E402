"""
=============================================================================
STUDYPULSE AI — LANGGRAPH NODE IMPLEMENTATIONS (REFACTORED)
=============================================================================
Changes from v1:
1. PII masking moved to dedicated Python preprocessing node (not in LLM prompt)
2. Date formatting done in Python node (not by LLM)
3. LLM calls use .with_structured_output(PydanticModel) — no JSON in prompt
4. Each LLM node injects only BASE_PERSONA + its task-specific sub-prompt
5. Non-LLM nodes are pure Python — no prompt tokens consumed
=============================================================================
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from .state import (
    StudyPulseState,
    ExtractedItem,
    ChatResponse,
    EvidenceEntry,
    DailyReminder,
    FlowType,
    Language,
    ItemCategory,
    Priority,
    IntentType,
    SourcePlatform,
)
from .system_prompt import (
    get_base_persona,
    get_extraction_prompt,
    get_rag_agent_tool_guidance,
    get_rag_agent_finalize_prompt,
    get_evidence_prompt,
    get_hitl_prompt,
    get_reminder_prompt,
    BOUNDARY_RULES_SHORT,
    CONFIDENCE_AUTO_APPROVE,
    CONFIDENCE_WARN,
    CONFIDENCE_CLARIFY,
    CONFIDENCE_REJECT,
    NOT_FOUND_MESSAGE,
)
from .rag_tools import RAG_TOOL_DECLARATIONS, execute_rag_tool, items_to_citations


# ═══════════════════════════════════════════════════════════════════════════
# HELPER: Trace updater
# ═══════════════════════════════════════════════════════════════════════════

def _trace(state: StudyPulseState, node_name: str) -> dict:
    """Append node name to metadata trace."""
    metadata = dict(state.get("metadata", {}))
    metadata["node_trace"] = metadata.get("node_trace", []) + [node_name]
    return metadata


# ═══════════════════════════════════════════════════════════════════════════
# PYTHON PREPROCESSING: PII MASKING NODE (no LLM, no tokens)
# ═══════════════════════════════════════════════════════════════════════════

_PII_RULES = [
    # Phone numbers (VN)
    (re.compile(r"\b(0\d{9,10})\b"), "[PHONE_MASKED]"),
    (re.compile(r"\b(\+84\d{9,10})\b"), "[PHONE_MASKED]"),
    # CMND/CCCD (9 or 12 digits)
    (re.compile(r"\b(\d{9}|\d{12})\b"), "[ID_MASKED]"),
    # Passwords in context
    (re.compile(r"(?i)(password|mật khẩu|pass)\s*[:=]\s*\S+"), r"\1: [CREDENTIAL_MASKED]"),
]


def _mask_pii(text: str) -> str:
    """Pure Python PII masking — deterministic, no LLM needed."""
    for pattern, replacement in _PII_RULES:
        text = pattern.sub(replacement, text)
    return text


def _mask_email(email: str) -> str:
    """Mask email local part: h***@domain.com"""
    if "@" not in email:
        return email
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


# ═══════════════════════════════════════════════════════════════════════════
# PYTHON PREPROCESSING: DATE FORMATTER NODE (no LLM, no tokens)
# ═══════════════════════════════════════════════════════════════════════════

def _format_date_vi(iso_date: str | None) -> str:
    """Format ISO date to Vietnamese display format."""
    if not iso_date:
        return "Chưa xác định"
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        weekdays_vi = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
        return f"{weekdays_vi[dt.weekday()]}, {dt.strftime('%d/%m/%Y')}"
    except (ValueError, TypeError):
        return iso_date


def _format_date_en(iso_date: str | None) -> str:
    """Format ISO date to English display format."""
    if not iso_date:
        return "TBD"
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%A, %b %d, %Y")
    except (ValueError, TypeError):
        return iso_date


def _format_date(iso_date: str | None, language: str) -> str:
    """Format date based on detected language."""
    return _format_date_vi(iso_date) if language == "vi" else _format_date_en(iso_date)


# ═══════════════════════════════════════════════════════════════════════════
# NODE 1: INGESTION NODE (Pure Python — 0 tokens)
# ═══════════════════════════════════════════════════════════════════════════

def ingestion_node(state: StudyPulseState) -> StudyPulseState:
    """
    Entry point. Normalize raw payloads, run PII masking in Python.
    NO LLM call — pure preprocessing.
    """
    raw = state.get("raw_payload", {})
    user_query = state.get("user_query", "")
    source = raw.get("source_platform", "direct_input")

    # PII masking in Python (NOT in LLM prompt)
    text_content = raw.get("body", "") or raw.get("content", "") or user_query
    masked_text = _mask_pii(text_content)

    metadata = {
        "ingestion_timestamp": datetime.utcnow().isoformat(),
        "source_platform": source,
        "node_trace": ["ingestion_node"],
        "pii_masked": True,
        "original_length": len(text_content),
        "masked_length": len(masked_text),
    }

    return {
        **state,
        "raw_payload": {**raw, "body_masked": masked_text, "original_length": len(text_content)},
        "user_query": user_query if user_query else masked_text,
        "extracted_items": state.get("extracted_items", []),
        "dashboard_timeline": state.get("dashboard_timeline", []),
        "evidence_log": state.get("evidence_log", []),
        "chat_history": state.get("chat_history", []),
        "user_profile": state.get("user_profile", {}),
        "confidence_score": 0.0,
        "requires_hitl": False,
        "hitl_items": [],
        "retry_count": state.get("retry_count", 0),
        "max_retries": state.get("max_retries", 3),
        "error_message": "",
        "final_response": "",
        "metadata": metadata,
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 2: LANGUAGE DETECT NODE (Pure Python — 0 tokens)
# ═══════════════════════════════════════════════════════════════════════════

_VI_PATTERN = re.compile(
    r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)


def language_detect_node(state: StudyPulseState) -> StudyPulseState:
    """Detect VI/EN from diacritical markers. Pure Python — 0 tokens."""
    text = state.get("user_query", "")
    sample = " ".join(text.split()[:50])
    vi_count = len(_VI_PATTERN.findall(sample))
    detected = "vi" if vi_count >= 3 else "en"

    metadata = _trace(state, "language_detect_node")
    metadata["vi_diacritical_count"] = vi_count

    return {**state, "language": detected, "metadata": metadata}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 3: INTENT ROUTER NODE (Pure Python — 0 tokens)
# ═══════════════════════════════════════════════════════════════════════════

_FLOW_KEYWORDS: dict[str, list[str]] = {
    "spam_rescue": ["spam", "thư rác", "rescue", "cứu mail"],
    "survey_log": ["khảo sát", "survey", "feedback", "phản hồi"],
    "daily_reminder": ["nhắc", "reminder", "deadline ngày mai"],
}

_INTENT_KEYWORDS: dict[str, list[str]] = {
    "query_timeline": ["lịch", "timeline", "schedule", "thời gian"],
    "query_material": ["tài liệu", "bài giảng", "material", "slide"],
    "query_deadline": ["deadline", "hạn nộp", "hạn chót", "nộp bài"],
}


def intent_router_node(state: StudyPulseState) -> StudyPulseState:
    """Classify flow_type + intent. Pure Python keyword matching — 0 tokens."""
    raw = state.get("raw_payload", {})
    query = state.get("user_query", "").lower()
    source = raw.get("source_platform", "direct_input")

    # Flow type classification
    if state.get("flow_type"):
        flow_type = state["flow_type"]
    elif source in ("gmail", "outlook", "discord") and not query.strip():
        flow_type = "ingestion"
    else:
        flow_type = "chat"  # default
        for ft, keywords in _FLOW_KEYWORDS.items():
            if any(kw in query for kw in keywords):
                flow_type = ft
                break

    # Sub-intent for chat flows
    intent = "general"
    if flow_type == "chat":
        for it, keywords in _INTENT_KEYWORDS.items():
            if any(kw in query for kw in keywords):
                intent = it
                break

    metadata = _trace(state, "intent_router_node")
    return {**state, "flow_type": flow_type, "intent": intent, "metadata": metadata}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 4: AI EXTRACTION NODE (LLM call — uses BASE_PERSONA + EXTRACTION_PROMPT)
# Uses .with_structured_output(ExtractionResult) — no JSON schema in prompt
# ═══════════════════════════════════════════════════════════════════════════

from pydantic import BaseModel, Field
from typing import Optional


class LLMExtractedItem(BaseModel):
    """Pydantic model passed to .with_structured_output() — replaces JSON in prompt."""
    category: str = Field(description="deadline|schedule|assignment|announcement|exam|other")
    title: str = Field(description="Extracted title, max 200 chars")
    description: str = Field(default="", description="Brief description, max 1000 chars")
    due_date: Optional[str] = Field(default=None, description="ISO 8601 date or null")
    due_time: Optional[str] = Field(default=None, description="HH:MM or null")
    time_unspecified: bool = Field(default=False, description="True if no time in source")
    priority: str = Field(default="medium", description="critical|high|medium|low")
    confidence_score: float = Field(description="0.0-1.0 extraction confidence")
    requires_clarification: bool = Field(default=False, description="Ambiguous date/info")
    conflict_detected: bool = Field(default=False, description="Conflicting sources found")
    meeting_link: Optional[str] = Field(default=None, description="Zoom/Meet URL if present, else null")
    naming_convention: Optional[str] = Field(default=None, description="Naming rules for submission if present, else null")
    required_materials: Optional[str] = Field(default=None, description="Documents/files/websites to open/read/prepare, else null")


class ExtractionResult(BaseModel):
    """Top-level structured output for extraction — passed to LLM via API schema."""
    items: list[LLMExtractedItem] = Field(default_factory=list)


def ai_extraction_node(state: StudyPulseState) -> StudyPulseState:
    """
    LLM extraction using:
    - system message: BASE_PERSONA only (~120 tokens, cacheable)
    - user message: EXTRACTION_PROMPT with runtime context
    - provider.parse(ExtractionResult) -> Pydantic enforced at API level, via
      providers.OpenAIProvider (see providers/openai_provider.py) rather than
      a LangChain chat model, so this stays on the same vendor as the rest
      of the agent.
    """
    raw = state.get("raw_payload", {})
    text = raw.get("body_masked", state.get("user_query", ""))
    source = raw.get("source_platform", "direct_input")
    language = state.get("language", "vi")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    current_year = datetime.utcnow().year

    # ── PRODUCTION LLM CALL ──
    from providers import make_provider

    provider = make_provider("openai")
    result: ExtractionResult = provider.parse(
        [
            {"role": "system", "content": get_base_persona()},  # ~120 tokens, CACHED
            {"role": "user", "content": get_extraction_prompt(  # Task-specific, fresh
                text=text,
                source_platform=source,
                today=today,
                current_year=current_year,
            )},
        ],
        response_format=ExtractionResult,
    )
    extracted_items = [
        ExtractedItem(
            source_platform=(
                SourcePlatform(source)
                if source in [e.value for e in SourcePlatform]
                else SourcePlatform.DIRECT_INPUT
            ),
            source_message_id=raw.get("message_id", str(uuid.uuid4())),
            source_url=raw.get("source_url", ""),
            language_detected=Language(language),
            pii_masked=True,
            raw_snippet=text[:2000],
            meeting_link=item.meeting_link,
            naming_convention=item.naming_convention,
            required_materials=item.required_materials,
            category=item.category,
            title=item.title,
            description=item.description,
            due_date=item.due_date,
            due_time=item.due_time,
            time_unspecified=item.time_unspecified,
            priority=item.priority,
            confidence_score=item.confidence_score,
            requires_clarification=item.requires_clarification,
            conflict_detected=item.conflict_detected,
        ).model_dump()
        for item in result.items
    ]

    # Aggregate confidence
    avg_conf = (
        sum(i.get("confidence_score", 0) for i in extracted_items) / len(extracted_items)
        if extracted_items else 0.0
    )

    # Flag HITL items
    hitl_items = [i for i in extracted_items if i.get("confidence_score", 0) < CONFIDENCE_WARN]

    metadata = _trace(state, "ai_extraction_node")
    metadata["items_extracted"] = len(extracted_items)
    metadata["items_needing_hitl"] = len(hitl_items)
    metadata["prompt_architecture"] = "base_persona(cached) + extraction_subprompt"

    return {
        **state,
        "extracted_items": extracted_items,
        "confidence_score": round(avg_conf, 3),
        "requires_hitl": len(hitl_items) > 0,
        "hitl_items": hitl_items,
        "metadata": metadata,
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 5: VALIDATION GUARDRAIL NODE (Pure Python — 0 tokens)
# Date sanity, duplicates, confidence thresholds — all deterministic
# ═══════════════════════════════════════════════════════════════════════════

def validation_guardrail_node(state: StudyPulseState) -> StudyPulseState:
    """Pure Python validation — no LLM, no tokens consumed."""
    items = state.get("extracted_items", [])
    dashboard = state.get("dashboard_timeline", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if retry_count >= max_retries:
        metadata = _trace(state, "validation_guardrail_node")
        return {
            **state,
            "error_message": f"Max retries ({max_retries}) exceeded. Escalating to HITL.",
            "requires_hitl": True,
            "metadata": metadata,
        }

    validated, rejected = [], []
    now = datetime.utcnow()
    grace = now - timedelta(days=1)
    existing_titles = {d.get("title", "").lower() for d in dashboard}
    valid_categories = {c.value for c in ItemCategory}

    for item in items:
        issues = []
        if not item.get("title", "").strip():
            issues.append("empty_title")

        due = item.get("due_date")
        if due:
            try:
                due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                if due_dt < grace:
                    issues.append("date_in_past")
            except (ValueError, TypeError):
                issues.append("invalid_date_format")

        if item.get("category") not in valid_categories:
            issues.append("invalid_category")
        if item.get("title", "").lower() in existing_titles:
            issues.append("duplicate_detected")
        if item.get("confidence_score", 0) < CONFIDENCE_REJECT:
            issues.append("below_minimum_confidence")

        if issues:
            item["validation_issues"] = issues
            rejected.append(item)
        else:
            validated.append(item)

    hitl_items = [i for i in validated if i.get("confidence_score", 0) < CONFIDENCE_WARN]
    confirmed = [i for i in validated if i.get("confidence_score", 0) >= CONFIDENCE_WARN]

    metadata = _trace(state, "validation_guardrail_node")
    metadata["validated_count"] = len(confirmed)
    metadata["rejected_count"] = len(rejected)

    return {
        **state,
        "extracted_items": confirmed,
        "hitl_items": state.get("hitl_items", []) + hitl_items + rejected,
        "requires_hitl": len(hitl_items) > 0 or len(rejected) > 0,
        "metadata": metadata,
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 6: DASHBOARD SYNC NODE (Pure Python — 0 tokens + SQLite Persistence)
# ═══════════════════════════════════════════════════════════════════════════

def dashboard_sync_node(state: StudyPulseState) -> StudyPulseState:
    """Append-only merge to timeline. Pure Python + SQLite persistence."""
    confirmed = state.get("extracted_items", [])
    existing = state.get("dashboard_timeline", [])
    updated = existing + confirmed
    updated.sort(key=lambda x: x.get("due_date") or "9999-12-31")

    # Persist new items to SQLite physical storage
    if confirmed:
        try:
            from .storage import get_db
            db = get_db()
            saved_count = db.save_timeline_items(confirmed)
            print(f"  [SQLite] Persisted {saved_count}/{len(confirmed)} timeline items to disk.")
        except Exception as e:
            print(f"  [SQLite] Warning: Failed to persist timeline items: {e}")

    # Index new items into FAISS vector store for RAG retrieval
    if confirmed:
        try:
            from .vector_store import get_vector_store
            vs = get_vector_store()
            indexed = vs.index_timeline_items(confirmed)
            print(f"  [FAISS] Indexed {indexed} items into vector store.")
        except Exception as e:
            print(f"  [FAISS] Warning: Failed to index items: {e}")

    metadata = _trace(state, "dashboard_sync_node")
    metadata["dashboard_total"] = len(updated)
    metadata["sqlite_persisted"] = len(confirmed)

    return {**state, "dashboard_timeline": updated, "metadata": metadata}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 7: RAG CHATBOT NODE (agentic — LLM decides when to call
# search_timeline / query_timeline, see rag_tools.py, instead of always
# being handed one fixed similarity_search(k=3) regardless of the question)
# ═══════════════════════════════════════════════════════════════════════════

MAX_RAG_TOOL_ROUNDS = 10


def rag_chatbot_node(state: StudyPulseState) -> StudyPulseState:
    """
    RAG chatbot with:
    - Agentic retrieval: the LLM calls search_timeline (semantic) and/or
      query_timeline (exact platform/category/priority filter) as needed,
      possibly more than once, instead of one fixed pre-stuffed context —
      see rag_tools.py's docstring for why two tools instead of one.
    - Token Usage Tracking (monitors LLM cost, summed across tool rounds).
    - Short-Term Memory: Prepend previous chat history to LLM messages.
    - Long-Term Memory: Prepend user profile context to the first user turn.
    """
    query = state.get("user_query", "")
    language = state.get("language", "vi")
    intent = state.get("intent", "general")
    timeline = state.get("dashboard_timeline", [])
    user_profile = dict(state.get("user_profile", {}))
    chat_history = list(state.get("chat_history", []))

    # 1. Long-Term Memory (Python preprocessing: Extract profile name/id from query)
    name_match = re.search(r"(?:tôi là|tên tôi là|mình tên là|tên mình là)\s*([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐ][a-zàáâãèéêìíòóôõùúýđ]*(?:\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐ][a-zàáâãèéêìíòóôõùúýđ]*)*)", query, re.IGNORECASE)
    if name_match:
        user_profile["user_name"] = name_match.group(1).strip()

    id_match = re.search(r"(?:mã học viên|mã số học viên|ms hv|mshv)[:\s]*([A-Za-z0-9\-]+)", query, re.IGNORECASE)
    if id_match:
        user_profile["student_id"] = id_match.group(1).strip()

    # Items confirmed earlier in THIS SAME graph run (an ingestion flow that
    # also happens to chat) — searchable immediately, on top of whatever
    # vector_store._bootstrap_from_sqlite already loaded from prior runs.
    if timeline:
        try:
            from .vector_store import get_vector_store
            get_vector_store().index_timeline_items(timeline)
        except Exception as e:
            print(f"  [FAISS] Failed to index current-run timeline items: {e}")

    from providers import make_provider

    provider = make_provider("openai")
    model_name = provider.default_model

    # 2. Short-Term Memory: previous chat history, as plain OpenAI-style messages
    messages: list[dict[str, str]] = [
        {"role": "system", "content": get_base_persona() + "\n" + get_rag_agent_tool_guidance()},
    ]
    for msg in chat_history:
        role = "user" if msg.get("role") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("content", "")})

    profile_context = f"USER PROFILE (LONG-TERM MEMORY): {json.dumps(user_profile)}\n" if user_profile else ""
    messages.append({"role": "user", "content": profile_context + query})

    # ── AGENTIC TOOL LOOP — LLM decides if/when/how many times to call
    # search_timeline / query_timeline before answering. Tool results are
    # fed back as plain user-role JSON blobs (not native tool_calls/tool-role
    # messages) so this stays on the same Provider.complete()/ToolCall
    # shape the rest of the codebase uses — no per-call ids to track. ──
    sources_cited: list[dict[str, str]] = []
    timeline_items_referenced: list[str] = []
    seen_citation_keys: set[str] = set()
    tool_calls_made: list[dict[str, Any]] = []
    round_responses: list[Any] = []

    for _round in range(MAX_RAG_TOOL_ROUNDS):
        response = provider.complete(messages, tools=RAG_TOOL_DECLARATIONS, model=model_name, temperature=0.2)
        round_responses.append(response)
        print(f"  [RAG] round {_round}: {len(response.tool_calls)} tool call(s)"
              + (f" -> {[c.name for c in response.tool_calls]}" if response.tool_calls else " (stopping)"))
        if not response.tool_calls:
            break

        call_summary = [{"name": c.name, "args": c.args} for c in response.tool_calls]
        messages.append({
            "role": "assistant",
            "content": f"{response.text or ''}\n\nTOOL_CALLS_JSON:\n{json.dumps(call_summary, ensure_ascii=False)}",
        })

        tool_events = []
        for call in response.tool_calls:
            tool_calls_made.append({"name": call.name, "args": call.args})
            result_text, items = execute_rag_tool(call.name, call.args)
            print(f"  [RAG]   {call.name}({call.args}) -> {len(items)} item(s)")
            tool_events.append({"tool": call.name, "args": call.args, "result": json.loads(result_text)})

            for item_id, citation in items_to_citations(items):
                key = item_id or citation["label"]
                if not key or key in seen_citation_keys:
                    continue
                seen_citation_keys.add(key)
                if item_id:
                    timeline_items_referenced.append(item_id)
                sources_cited.append(citation)

        messages.append({
            "role": "user",
            "content": (
                f"TOOL_RESULTS_JSON:\n{json.dumps(tool_events, ensure_ascii=False)}\n\n"
                "Call another tool if this doesn't fully answer the question, "
                "otherwise answer now using only these results."
            ),
        })

    # ── FINALIZE — one structured-output call for the ChatResponse shape
    # the FE depends on, grounded in whatever the tool rounds above found. ──
    messages.append({"role": "user", "content": get_rag_agent_finalize_prompt(query=query, language=language)})
    result: ChatResponse = provider.parse(messages, response_format=ChatResponse, temperature=0.2)
    response_text = result.response_text

    # A tool call returning results doesn't mean those results actually
    # answered the question — the model can (correctly) judge them
    # irrelevant and still fall back to NOT_FOUND_MESSAGE in response_text.
    # sources_cited/timeline_items_referenced are accumulated from every
    # tool call unconditionally above, so without this they'd show a
    # citation for an item the reply just said wasn't found. Treat the
    # fallback message as authoritative: no citations when it's used.
    if response_text.strip() == NOT_FOUND_MESSAGE.get(language, "").strip():
        sources_cited = []
        timeline_items_referenced = []

    # ── TOKEN USAGE TRACKING (summed across every round + the finalize call) ──
    token_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    try:
        est_input = 0
        for m in messages:
            est_input += len(m["content"]) // 4  # ~4 chars per token estimate
        est_output = sum(len(r.text or "") for r in round_responses) // 4 + len(response_text) // 4
        token_usage = {
            "input_tokens": est_input,
            "output_tokens": est_output,
            "total_tokens": est_input + est_output,
        }
        print(f"  [Tokens] Estimated usage: input={est_input}, output={est_output}, total={est_input + est_output}")

        # Persist to SQLite
        from .storage import get_db
        db = get_db()
        db.log_token_usage(
            node_name="rag_chatbot_node",
            input_tokens=est_input,
            output_tokens=est_output,
            model_name=model_name,
        )
    except Exception as e:
        print(f"  [Tokens] Warning: Failed to track token usage: {e}")

    # Update state history with the current turn
    current_turn = [
        {"role": "user", "content": query},
        {"role": "assistant", "content": response_text}
    ]

    chat_resp = ChatResponse(
        language=Language(language),
        intent=IntentType(intent) if intent in [e.value for e in IntentType] else IntentType.GENERAL,
        response_text=response_text,
        confidence=0.9,
        sources_cited=sources_cited,
        timeline_items_referenced=timeline_items_referenced,
    ).model_dump()

    metadata = _trace(state, "rag_chatbot_node")
    metadata["prompt_architecture"] = "base_persona(cached) + short_term_history + long_term_profile + agentic_rag_tools"
    metadata["token_usage"] = token_usage
    metadata["rag_source"] = "agentic_tools"
    metadata["rag_tool_calls"] = tool_calls_made

    return {
        **state,
        "chat_response": chat_resp,
        "final_response": response_text,
        "chat_history": chat_history + current_turn,
        "user_profile": user_profile,
        "metadata": metadata,
    }


# ═══════════════════════════════════════════════════════════════════════════
# NODE 8: USER EVIDENCE LOG NODE (Python preprocessing + minimal LLM)
# PII masking done in Python BEFORE any LLM confirmation call
# ═══════════════════════════════════════════════════════════════════════════

def user_evidence_log_node(state: StudyPulseState) -> StudyPulseState:
    """
    Log survey responses VERBATIM.
    PII masking: Python preprocessing (not LLM).
    Confirmation message: can use LLM or static template.
    """
    query = state.get("user_query", "")
    raw = state.get("raw_payload", {})
    language = state.get("language", "vi")

    survey_question = raw.get("survey_question", "Phản hồi trải nghiệm học tập")
    respondent_email = raw.get("respondent_email", "unknown@student.vinai.edu.vn")

    # PII masking in PYTHON (not LLM) — deterministic, no token cost
    masked_email = _mask_email(respondent_email)
    pii_fields = []
    verbatim = query
    if re.search(r"\b\d{9,12}\b", verbatim):
        verbatim = re.sub(r"\b\d{9,12}\b", "[PHONE_MASKED]", verbatim)
        pii_fields.append("phone_number")
    if re.search(r"password|mật khẩu", verbatim, re.IGNORECASE):
        verbatim = re.sub(r"(?i)(password|mật khẩu)\s*[:=]\s*\S+", r"\1: [CREDENTIAL_MASKED]", verbatim)
        pii_fields.append("password")

    entry = EvidenceEntry(
        respondent_email_masked=masked_email,
        survey_question=survey_question,
        verbatim_text=verbatim,  # IMMUTABLE
        language_detected=Language(language),
        source="direct_input",
        pii_masked_fields=pii_fields,
    ).model_dump()

    evidence_log = state.get("evidence_log", []) + [entry]

    # Persist evidence entry to SQLite physical storage
    try:
        from .storage import get_db
        db = get_db()
        if db.save_evidence_entry(entry):
            print(f"  [SQLite] Persisted evidence entry {entry['id'][:8]}... to disk.")
    except Exception as e:
        print(f"  [SQLite] Warning: Failed to persist evidence entry: {e}")

    # Static confirmation (no LLM needed for this)
    confirmation = (
        f"Đã ghi nhận phản hồi của (ID: {entry['id'][:8]}...). BTC sẽ xem xét và phản hồi sớm nhất có thể ạ!"
        if language == "vi"
        else f"Verbatim feedback recorded (ID: {entry['id'][:8]}...). Thank you!"
    )

    metadata = _trace(state, "user_evidence_log_node")
    metadata["evidence_entries_total"] = len(evidence_log)
    metadata["pii_masked_in"] = "python_node"
    metadata["sqlite_persisted"] = True

    return {**state, "evidence_log": evidence_log, "final_response": confirmation, "metadata": metadata}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 9: HITL ESCALATION NODE (Python formatting — 0 tokens)
# ═══════════════════════════════════════════════════════════════════════════

def hitl_escalation_node(state: StudyPulseState) -> StudyPulseState:
    """Format escalation message. Pure Python — no LLM tokens."""
    hitl_items = state.get("hitl_items", [])
    language = state.get("language", "vi")
    error_msg = state.get("error_message", "")

    if not hitl_items and not error_msg:
        metadata = _trace(state, "hitl_escalation_node (skip)")
        return {**state, "metadata": metadata}

    escalation_details = []
    for item in hitl_items:
        issues = item.get("validation_issues", [])
        conf = item.get("confidence_score", 0)
        escalation_details.append(
            f"- [{item.get('category', '?')}] {item.get('title', 'N/A')} | "
            f"confidence: {conf:.2f} | issues: {', '.join(issues) if issues else 'low_confidence'}"
        )

    details_text = "\n".join(escalation_details) if escalation_details else error_msg

    if language == "vi":
        response = (
            f"**Cần xác nhận từ TA/giảng viên**\n\n"
            f"Các mục sau có thông tin hơn mơ hồ:\n\n"
            f"{details_text}\n\n"
            f"Vui lòng xác nhận hoặc chỉnh sửa trước khi thêm vào timeline."
        )
    else:
        response = (
            f"**TA/Instructor Review Required**\n\n"
            f"The following items have low confidence or need manual verification:\n\n"
            f"{details_text}\n\n"
            f"Please confirm or edit before adding to the timeline."
        )

    metadata = _trace(state, "hitl_escalation_node")
    metadata["escalation_count"] = len(hitl_items)

    return {**state, "final_response": response, "metadata": metadata}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 10: RESPONSE FORMATTER NODE (Python postprocessing — 0 tokens)
# Date formatting done here in Python, not by LLM
# ═══════════════════════════════════════════════════════════════════════════

def response_formatter_node(state: StudyPulseState) -> StudyPulseState:
    """Format final response. Date formatting in Python. No LLM tokens."""
    language = state.get("language", "vi")
    flow_type = state.get("flow_type", "chat")
    final = state.get("final_response", "")

    if not final:
        if flow_type == "ingestion":
            items = state.get("extracted_items", [])
            hitl = state.get("hitl_items", [])
            if language == "vi":
                final = (
                    f"Đã trích xuất {len(items)} mục từ nguồn.\n"
                    f"Đã thêm vào timeline: {len(items)}\n"
                    f"Cần xác nhận: {len(hitl)}"
                )
            else:
                final = (
                    f"Extracted {len(items)} items from source.\n"
                    f"Added to timeline: {len(items)}\n"
                    f"Needs confirmation: {len(hitl)}"
                )
        else:
            final = (
                "Xin lỗi, tôi không tìm thấy thông tin phù hợp."
                if language == "vi"
                else "Sorry, I couldn't find relevant information."
            )

    metadata = _trace(state, "response_formatter_node")
    metadata["response_timestamp"] = datetime.utcnow().isoformat()

    return {**state, "final_response": final, "metadata": metadata}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 11: SPAM RESCUE NODE (can use LLM for classification)
# ═══════════════════════════════════════════════════════════════════════════

def spam_rescue_node(state: StudyPulseState) -> StudyPulseState:
    """Scan spam folders. LLM optional for classification."""
    language = state.get("language", "vi")
    rescued_count = 0  # Mock

    if language == "vi":
        response = (
            f"Đã quét thư mục Spam/Junk.\n"
            f"Phát hiện {rescued_count} email học tập quan trọng.\n"
            f"Các email đã được di chuyển về hộp thư chính."
        )
    else:
        response = (
            f"Scanned Spam/Junk folder.\n"
            f"Found {rescued_count} important academic emails.\n"
            f"Emails have been moved to your main inbox."
        )

    metadata = _trace(state, "spam_rescue_node")
    return {**state, "final_response": response, "metadata": metadata}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 12: DAILY REMINDER NODE (Python aggregation + optional LLM polish)
# ═══════════════════════════════════════════════════════════════════════════

def daily_reminder_node(state: StudyPulseState) -> StudyPulseState:
    """Generate next-day reminder. Aggregates in Python, summarizes with LLM."""
    language = state.get("language", "vi")
    timeline = state.get("dashboard_timeline", [])
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

    tomorrow_items = [i for i in timeline if i.get("due_date", "")[:10] == tomorrow]
    critical = [i for i in tomorrow_items if i.get("priority") == "critical"]

    msg = ""
    if tomorrow_items:
        # Prepare list for LLM query
        items_for_llm = []
        for i in tomorrow_items:
            items_for_llm.append({
                "title": i.get("title", ""),
                "priority": i.get("priority", "medium"),
                "due_time": i.get("due_time") or "TBD",
                "description": i.get("description", ""),
                "raw_snippet": i.get("raw_snippet", "")
            })

        from providers import make_provider

        provider = make_provider("openai")

        prompt_text = get_reminder_prompt(
            target_date=tomorrow,
            items_json=json.dumps(items_for_llm, ensure_ascii=False),
            language=language
        )

        try:
            response = provider.complete(
                [
                    {
                        "role": "system",
                        "content": get_base_persona() + "\nRule: Never use emojis, icons or visual symbols in the output message. Keep it clean and text-only.",
                    },
                    {"role": "user", "content": prompt_text},
                ],
                temperature=0.3,
            )
            msg = (response.text or "").strip()
            print(f"  [DailyReminder] Generated with LLM summary.")
        except Exception as e:
            print(f"  [DailyReminder] LLM call failed, falling back: {e}")
            msg = ""

    # Fallback/Empty message
    if not msg:
        if language == "vi":
            if tomorrow_items:
                items_text = "\n".join(
                    f"  {'[QUAN TRỌNG]' if i.get('priority') == 'critical' else '[LỊCH TRÌNH]'} "
                    f"{i['title']} — {i.get('due_time') or 'chưa rõ giờ'}"
                    for i in tomorrow_items
                )
                msg = (
                    f"**Nhắc nhở deadline ngày mai ({_format_date(tomorrow, 'vi')})**\n\n"
                    f"Bạn có {len(tomorrow_items)} mục cần hoàn thành "
                    f"({len(critical)} quan trọng):\n\n{items_text}"
                )
            else:
                msg = f"Không có deadline nào vào ngày mai ({_format_date(tomorrow, 'vi')}). Nghỉ ngơi nhé!"
        else:
            if tomorrow_items:
                items_text = "\n".join(
                    f"  {'[CRITICAL]' if i.get('priority') == 'critical' else '[SCHEDULE]'} "
                    f"{i['title']} — {i.get('due_time') or 'time TBD'}"
                    for i in tomorrow_items
                )
                msg = (
                    f"**Tomorrow's Deadline Reminder ({_format_date(tomorrow, 'en')})**\n\n"
                    f"You have {len(tomorrow_items)} items due "
                    f"({len(critical)} critical):\n\n{items_text}"
                )
            else:
                msg = f"No deadlines tomorrow ({_format_date(tomorrow, 'en')}). Rest well!"

    reminder = DailyReminder(
        target_date=tomorrow,
        language=Language(language),
        items=[ExtractedItem(**i) for i in tomorrow_items] if tomorrow_items else [],
        total_items=len(tomorrow_items),
        critical_count=len(critical),
        message_text=msg,
    ).model_dump()

    metadata = _trace(state, "daily_reminder_node")
    metadata["reminder_generator"] = "llm_summary"
    
    return {**state, "daily_reminder": reminder, "final_response": msg, "metadata": metadata}


# ═══════════════════════════════════════════════════════════════════════════
# NODE 13: EMERGENCY ALERT NODE (Pure Python — 0 tokens)
# ═══════════════════════════════════════════════════════════════════════════

def emergency_alert_node(state: StudyPulseState) -> StudyPulseState:
    """
    Emergency Alert Node (Pure Python, 0 tokens).
    Formats next-step actions, materials, naming rules, and links for due tasks.
    """
    language = state.get("language", "vi")
    items = state.get("dashboard_timeline", []) or state.get("extracted_items", [])
    
    if not items:
        msg = "Không tìm thấy thông tin deadline cần nhắc nhở." if language == "vi" else "No upcoming deadline details found."
        metadata = _trace(state, "emergency_alert_node")
        return {**state, "final_response": msg, "metadata": metadata}
        
    item = items[0]
    title = item.get("title", "")
    desc = item.get("description", "")
    materials = item.get("required_materials")
    naming = item.get("naming_convention")
    link = item.get("meeting_link")
    
    if language == "vi":
        msg = (
            f"**THÔNG BÁO KHẨN CẤP**\n"
            f"Hạn chót cho mục sau chỉ còn đúng 10 phút nữa:\n"
            f"**{title}**\n"
        )
        if desc:
            msg += f"Chi tiết: {desc}\n"
        msg += "\n"
        msg += f"Cần chuẩn bị:\n"
        msg += f"- Tài liệu cần mở: {materials or 'Không yêu cầu tài liệu cụ thể'}\n"
        msg += f"- Quy tắc đặt tên: {naming or 'Tự do đặt tên'}\n"
        msg += f"- Link Meet/Zoom: {link or 'Không có link phòng họp'}\n"
        msg += "\n"
        msg += "Nhanh tay lên kẻo trễ nhé!"
    else:
        msg = (
            f"**EMERGENCY ALERT**\n"
            f"The deadline for the following item is in 10 minutes:\n"
            f"**{title}**\n"
        )
        if desc:
            msg += f"Details: {desc}\n"
        msg += "\n"
        msg += f"What to prepare:\n"
        msg += f"- Required materials: {materials or 'No specific materials required'}\n"
        msg += f"- Naming convention: {naming or 'No specific naming convention'}\n"
        msg += f"- Meet/Zoom link: {link or 'No meeting link'}\n"
        msg += "\n"
        msg += "Hurry up before it's too late!"
        
    alert = {
        "alert_id": str(uuid.uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "item_id": item.get("id", ""),
        "message_text": msg
    }
    
    metadata = _trace(state, "emergency_alert_node")
    return {
        **state,
        "emergency_alert": alert,
        "final_response": msg,
        "metadata": metadata
    }

