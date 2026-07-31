"""
=============================================================================
STUDYPULSE AI — LANGGRAPH GRAPH DEFINITION (REFACTORED WITH CHECKPOINTER & HITL INTERRUPT)
=============================================================================
Compiles the full StateGraph with conditional routing, decision gates,
loop guards, persistent checkpointer factory, and HITL interrupt_before points.
=============================================================================
"""

from __future__ import annotations

import os
import threading
from typing import Any, List, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .state import StudyPulseState
from .nodes import (
    ingestion_node,
    language_detect_node,
    intent_router_node,
    ai_extraction_node,
    validation_guardrail_node,
    dashboard_sync_node,
    rag_chatbot_node,
    user_evidence_log_node,
    hitl_escalation_node,
    response_formatter_node,
    spam_rescue_node,
    daily_reminder_node,
    emergency_alert_node,
)
from .guardrail import guardrail_node
from .system_prompt import CONFIDENCE_WARN


# ═══════════════════════════════════════════════════════════════════════════
# CHECKPOINTER FACTORY (Production Persistence)
# ═══════════════════════════════════════════════════════════════════════════

def get_checkpointer(db_path: Optional[str] = None) -> BaseCheckpointSaver:
    """
    Checkpointer Factory for Production State Persistence.
    
    Why this is needed:
    - MemorySaver only keeps state in RAM. If server crashes or restarts,
      all pending HITL approvals and session states disappear.
    - SqliteSaver (or persistent file saver) stores thread state on disk/DB,
      allowing HITL review hours/days later across server restarts.
    """
    if db_path is None:
        db_path = os.getenv("GSD_CHECKPOINT_DB", "checkpoints.sqlite")

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3
        conn = sqlite3.connect(db_path, check_same_thread=False)
        return SqliteSaver(conn)
    except Exception:
        # Fallback to MemorySaver for lightweight or dev testing
        return MemorySaver()


# ═══════════════════════════════════════════════════════════════════════════
# CONDITIONAL EDGE FUNCTIONS (Decision Gates)
# ═══════════════════════════════════════════════════════════════════════════

def route_by_flow_type(state: StudyPulseState) -> str:
    """
    DECISION GATE 1: Route based on classified flow_type.
    """
    flow = state.get("flow_type", "chat")
    route_map = {
        "ingestion": "ai_extraction",
        "chat": "rag_chatbot",
        "survey_log": "user_evidence_log",
        "spam_rescue": "spam_rescue",
        "daily_reminder": "daily_reminder",
        "emergency_alert": "emergency_alert",
    }
    return route_map.get(flow, "rag_chatbot")


def route_by_confidence(state: StudyPulseState) -> str:
    """
    DECISION GATE 2: Route based on extraction confidence & HITL flag.
    """
    if state.get("retry_count", 0) >= state.get("max_retries", 3):
        return "hitl_escalation"

    if state.get("requires_hitl", False):
        return "hitl_escalation"

    confidence = state.get("confidence_score", 0.0)
    if confidence < CONFIDENCE_WARN:
        return "hitl_escalation"

    return "dashboard_sync"


def route_after_hitl(state: StudyPulseState) -> str:
    """
    DECISION GATE 3: After HITL, route to formatter (no retry loop).
    """
    return "response_formatter"


# ═══════════════════════════════════════════════════════════════════════════
# GRAPH BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def build_studypulse_graph() -> StateGraph:
    """
    Build the StudyPulse AI StateGraph.
    """
    graph = StateGraph(StudyPulseState)

    # ── REGISTER ALL NODES ──
    graph.add_node("ingestion", ingestion_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("language_detect", language_detect_node)
    graph.add_node("intent_router", intent_router_node)
    graph.add_node("ai_extraction", ai_extraction_node)
    graph.add_node("validation_guardrail", validation_guardrail_node)
    graph.add_node("dashboard_sync", dashboard_sync_node)
    graph.add_node("rag_chatbot", rag_chatbot_node)
    graph.add_node("user_evidence_log", user_evidence_log_node)
    graph.add_node("hitl_escalation", hitl_escalation_node)
    graph.add_node("response_formatter", response_formatter_node)
    graph.add_node("spam_rescue", spam_rescue_node)
    graph.add_node("daily_reminder", daily_reminder_node)
    graph.add_node("emergency_alert", emergency_alert_node)

    # ── STATIC PIPELINE: Ingestion → Guardrail → Conditional Gate ──
    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "guardrail")

    # ── SECURITY GATE: Guardrail → Safe/Blocked routing ──
    def route_by_guardrail(state: StudyPulseState) -> str:
        if state.get("guardrail_blocked", False):
            return "response_formatter"
        return "language_detect"

    graph.add_conditional_edges(
        "guardrail",
        route_by_guardrail,
        {
            "language_detect": "language_detect",
            "response_formatter": "response_formatter",
        },
    )

    graph.add_edge("language_detect", "intent_router")

    # ── DECISION GATE 1: IntentRouter → Conditional Branch ──
    graph.add_conditional_edges(
        "intent_router",
        route_by_flow_type,
        {
            "ai_extraction": "ai_extraction",
            "rag_chatbot": "rag_chatbot",
            "user_evidence_log": "user_evidence_log",
            "spam_rescue": "spam_rescue",
            "daily_reminder": "daily_reminder",
            "emergency_alert": "emergency_alert",
        },
    )

    # ── INGESTION PIPELINE: Extraction → Validation → Confidence Gate ──
    graph.add_edge("ai_extraction", "validation_guardrail")

    # ── DECISION GATE 2: Validation → Confidence Branch ──
    graph.add_conditional_edges(
        "validation_guardrail",
        route_by_confidence,
        {
            "dashboard_sync": "dashboard_sync",
            "hitl_escalation": "hitl_escalation",
        },
    )

    # ── CONVERGENCE: All paths → ResponseFormatter → END ──
    graph.add_edge("dashboard_sync", "response_formatter")

    # ── DECISION GATE 3: HITL → Formatter (no loop) ──
    graph.add_conditional_edges(
        "hitl_escalation",
        route_after_hitl,
        {
            "response_formatter": "response_formatter",
        },
    )

    # ── DIRECT PATHS: Chat/Evidence/Spam/Reminder → Formatter ──
    graph.add_edge("rag_chatbot", "response_formatter")
    graph.add_edge("user_evidence_log", "response_formatter")
    graph.add_edge("spam_rescue", "response_formatter")
    graph.add_edge("daily_reminder", "response_formatter")
    graph.add_edge("emergency_alert", "response_formatter")

    # ── TERMINAL: Formatter → END ──
    graph.add_edge("response_formatter", END)

    return graph


def compile_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    interrupt_before: Optional[List[str]] = None,
):
    """
    Compile the graph with Checkpointer and HITL interrupt points.
    
    Parameters:
    -----------
    checkpointer : BaseCheckpointSaver, optional
        Persistent Checkpointer instance (defaults to get_checkpointer()).
    interrupt_before : List[str], optional
        List of node names to pause execution BEFORE entering.
        Defaults to ["hitl_escalation"] to enable Human Approval for HITL items.
    """
    graph = build_studypulse_graph()

    if checkpointer is None:
        checkpointer = get_checkpointer()

    if interrupt_before is None:
        # Automatically pause BEFORE hitl_escalation node so TA/human can review & approve
        interrupt_before = ["hitl_escalation"]

    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )


# ═══════════════════════════════════════════════════════════════════════════
# GRAPH METADATA
# ═══════════════════════════════════════════════════════════════════════════

_compiled_graph: Any = None
_compiled_graph_lock = threading.Lock()


def get_compiled_graph() -> Any:
    """Process-wide singleton compiled graph, shared by server.py's chat
    endpoint and mail_ingest.py's background ingestion — one checkpointer
    DB connection and one FAISS/SQLite-backed set of nodes, not one per
    caller."""
    global _compiled_graph
    if _compiled_graph is None:
        with _compiled_graph_lock:
            if _compiled_graph is None:
                _compiled_graph = compile_graph()
    return _compiled_graph


GRAPH_METADATA = {
    "name": "StudyPulse AI — EduCentral Agent",
    "version": "2.1.0",
    "nodes": 14,
    "decision_gates": 4,
    "safeguards": {
        "max_retries": 3,
        "confidence_threshold": 0.85,
        "hitl_terminal": True,
        "interrupt_before": ["hitl_escalation"],
        "checkpointer": "SqliteSaver / MemorySaver",
        "guardrail": "dual_layer_regex_llm",
        "vector_store": "faiss_dynamic",
        "physical_storage": "sqlite_persistent",
    },
    "flow_types": ["ingestion", "chat", "survey_log", "spam_rescue", "daily_reminder"],
    "supported_platforms": ["gmail", "outlook", "discord", "direct_input"],
    "languages": ["vi", "en"],
}
