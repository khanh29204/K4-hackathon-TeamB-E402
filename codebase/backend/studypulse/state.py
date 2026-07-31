"""
=============================================================================
STUDYPULSE AI — STATE SCHEMA & TYPE DEFINITIONS (REFACTORED WITH CUSTOM REDUCER)
=============================================================================
LangGraph State TypedDict + Pydantic models for extraction, chat, evidence.
Includes Custom Deduplicating & Action-based Reducers to prevent duplication
during retries or multi-loop executions.
=============================================================================
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ═══════════════════════════════════════════════════════════════════════════
# CUSTOM REDUCER FUNCTIONS (Deduplication & Action-based)
# ═══════════════════════════════════════════════════════════════════════════

def dedupe_list_reducer(
    existing: List[Dict[str, Any]],
    update: Union[List[Dict[str, Any]], Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Custom Reducer for List State Fields in LangGraph.
    
    Replaces simple operator.add (list_a + list_b) to solve:
    1. Deduplication: Removes duplicate items based on 'id' or ('title' + 'due_date').
    2. Action-based updates:
       - {"action": "overwrite", "items": [...]}: Fully resets/replaces existing list.
       - {"action": "delete", "ids": [...]}: Removes specified items by ID.
       - List of items or {"action": "append", "items": [...]}: Merges & deduplicates.
    """
    if existing is None:
        existing = []

    # Handle action-based dictionary update
    if isinstance(update, dict):
        action = update.get("action", "append")
        if action == "overwrite":
            items = update.get("items", [])
            # Deduplicate overwrite items
            seen = set()
            res = []
            for item in items:
                item_key = item.get("id") or f"{item.get('title')}_{item.get('due_date')}"
                if item_key not in seen:
                    seen.add(item_key)
                    res.append(item)
            return res

        elif action == "delete":
            ids_to_remove = set(update.get("ids", []))
            return [item for item in existing if item.get("id") not in ids_to_remove]

        elif action == "append":
            new_items = update.get("items", [])
        else:
            new_items = [update]
    else:
        new_items = update if isinstance(update, list) else [update]

    # Deduplicate & merge new_items into existing list
    result = list(existing)
    existing_keys = {
        item.get("id") or f"{item.get('title')}_{item.get('due_date')}"
        for item in existing
    }

    for item in new_items:
        if not isinstance(item, dict):
            continue
        item_key = item.get("id") or f"{item.get('title')}_{item.get('due_date')}"
        if item_key not in existing_keys:
            existing_keys.add(item_key)
            result.append(item)
        else:
            # Update existing item in-place if new metadata is provided
            for idx, ex_item in enumerate(result):
                ex_key = ex_item.get("id") or f"{ex_item.get('title')}_{ex_item.get('due_date')}"
                if ex_key == item_key:
                    result[idx] = {**ex_item, **item}
                    break

    return result


def chat_history_reducer(
    existing: List[Dict[str, Any]],
    update: Union[List[Dict[str, Any]], Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Custom Reducer for Chat History in LangGraph (Short-Term Memory).
    Keeps only the last 6 messages to avoid token bloat while retaining context.
    """
    if existing is None:
        existing = []
    
    if isinstance(update, dict):
        new_msgs = [update]
    elif isinstance(update, list):
        new_msgs = update
    else:
        new_msgs = []
        
    result = list(existing) + list(new_msgs)
    # Keep only the last 6 messages for short-term conversation context
    return result[-6:]


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class SourcePlatform(str, Enum):
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    DISCORD = "discord"
    DIRECT_INPUT = "direct_input"


class ItemCategory(str, Enum):
    DEADLINE = "deadline"
    SCHEDULE = "schedule"
    ASSIGNMENT = "assignment"
    ANNOUNCEMENT = "announcement"
    EXAM = "exam"
    OTHER = "other"


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FlowType(str, Enum):
    INGESTION = "ingestion"
    CHAT = "chat"
    SURVEY_LOG = "survey_log"
    SPAM_RESCUE = "spam_rescue"
    DAILY_REMINDER = "daily_reminder"
    EMERGENCY_ALERT = "emergency_alert"


class Language(str, Enum):
    VI = "vi"
    EN = "en"


class IntentType(str, Enum):
    QUERY_TIMELINE = "query_timeline"
    QUERY_MATERIAL = "query_material"
    QUERY_DEADLINE = "query_deadline"
    GENERAL = "general"


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS — Extraction, Chat, Evidence
# ═══════════════════════════════════════════════════════════════════════════

class ExtractedItem(BaseModel):
    """Single extracted academic item from any source channel."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    source_platform: SourcePlatform
    source_message_id: str
    source_channel: str = ""
    category: ItemCategory
    title: str = Field(..., max_length=200)
    description: str = Field(default="", max_length=1000)
    due_date: Optional[str] = None  # ISO 8601
    due_time: Optional[str] = None  # HH:MM
    time_unspecified: bool = False
    recurrence: str = "none"
    priority: Priority = Priority.MEDIUM
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    requires_clarification: bool = False
    conflict_detected: bool = False
    conflicting_sources: List[str] = Field(default_factory=list)
    extracted_by: str = "studypulse_ai_v1"
    language_detected: Language = Language.VI
    pii_masked: bool = False
    raw_snippet: str = Field(default="", max_length=2000)
    meeting_link: Optional[str] = None
    naming_convention: Optional[str] = None
    required_materials: Optional[str] = None
    # Deep link back to the original message, when the ingesting module
    # could build one from IDs only it has in scope (thread_id for Gmail,
    # message_id for Outlook, guild_id+channel_id for Discord) — see
    # mail_ingest.py/discord_ingest.py's raw_payload construction. Empty for
    # direct_input or anything ingested before this field existed.
    source_url: str = ""


class SourceCitation(BaseModel):
    """label/url pair — was List[Dict[str, str]] on ChatResponse, but
    OpenAI's structured-output strict mode can't represent an open-ended
    Dict[str, str] map (no fixed `properties`), so this needs to be its own
    model with a fixed shape instead. Same {label, url} JSON on the wire
    either way (model_dump() flattens it back to a plain dict)."""
    label: str
    url: str = ""


class ChatResponse(BaseModel):
    """Structured response from the RAG chatbot node."""
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    language: Language
    intent: IntentType
    response_text: str
    sources_cited: List[SourceCitation] = Field(default_factory=list)
    timeline_items_referenced: List[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    requires_clarification: bool = False
    suggested_actions: List[str] = Field(default_factory=list)


class EvidenceEntry(BaseModel):
    """Verbatim survey/feedback evidence log entry."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    respondent_email_masked: str
    survey_question: str
    verbatim_text: str  # IMMUTABLE — exact user response
    language_detected: Language
    source: str = "direct_input"
    pii_masked_fields: List[str] = Field(default_factory=list)


class DailyReminder(BaseModel):
    """Consolidated next-day deadline reminder."""
    reminder_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    target_date: str  # YYYY-MM-DD
    scheduled_send_time: str = "08:00"
    language: Language = Language.VI
    items: List[ExtractedItem] = Field(default_factory=list)
    total_items: int = 0
    critical_count: int = 0
    message_text: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# LANGGRAPH STATE SCHEMA WITH ANNOTATED CUSTOM REDUCERS
# ═══════════════════════════════════════════════════════════════════════════

class StudyPulseState(TypedDict, total=False):
    """
    Central state object passed through all LangGraph nodes.
    Uses Custom dedupe_list_reducer for list attributes to prevent duplicates.
    """
    raw_payload: Dict[str, Any]
    user_query: str
    user_id: str
    language: str
    flow_type: str
    intent: str
    
    # Annotated list fields using dedupe_list_reducer
    extracted_items: Annotated[List[Dict[str, Any]], dedupe_list_reducer]
    dashboard_timeline: Annotated[List[Dict[str, Any]], dedupe_list_reducer]
    evidence_log: Annotated[List[Dict[str, Any]], dedupe_list_reducer]
    hitl_items: Annotated[List[Dict[str, Any]], dedupe_list_reducer]
    # Plain (last-write-wins) field, NOT chat_history_reducer: every node
    # that touches this (rag_chatbot_node) already computes and returns the
    # complete, already-capped-to-6 list, not a delta to append. Nodes that
    # don't touch chat_history spread **state in their return (a pattern
    # used throughout this file), which makes the key "present" on every
    # node's output even when unchanged — with an accumulating reducer that
    # meant chat_history_reducer fired on every node in the path and
    # doubled the history each time, corrupting multi-turn memory. Kept
    # chat_history_reducer defined below for reference/rollback, just no
    # longer wired in.
    chat_history: List[Dict[str, Any]]
    user_profile: Dict[str, Any]

    chat_response: Dict[str, Any]
    daily_reminder: Dict[str, Any]
    emergency_alert: Dict[str, Any]
    confidence_score: float
    requires_hitl: bool
    retry_count: int
    max_retries: int
    error_message: str
    guardrail_blocked: bool
    final_response: str
    metadata: Dict[str, Any]
