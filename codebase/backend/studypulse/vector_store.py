"""
=============================================================================
STUDYPULSE AI — DYNAMIC RAG VECTOR STORE (FAISS)
=============================================================================
Manages a FAISS-based vector index for semantic retrieval of timeline items,
evidence entries, and course documents. Falls back to static docs if FAISS
is unavailable.
=============================================================================
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """
    FAISS-backed vector store for dynamic RAG retrieval.
    
    Indexes timeline items, evidence entries, and course materials
    for semantic similarity search during chatbot interactions.
    """

    def __init__(self):
        self._store = None
        self._embeddings = None
        self._initialized = False
        self._fallback_docs = (
            "VinAI Academy Mini Hackathon Day 1 Foundation & Day 2 Specs. "
            "[T01-001] Introduction to AI Hackathon."
        )

    def _get_embeddings(self):
        """Lazy-init embeddings, routed through providers.OpenAIProvider so
        this stays on the same LLM vendor as the rest of the agent (no
        langchain-openai / langchain-google-genai dependency needed)."""
        if self._embeddings is None:
            try:
                from langchain_core.embeddings import Embeddings

                from providers import make_provider

                provider = make_provider("openai")

                class _ProviderEmbeddings(Embeddings):
                    def embed_documents(self, texts: list[str]) -> list[list[float]]:
                        return provider.embed(texts)

                    def embed_query(self, text: str) -> list[float]:
                        return provider.embed([text])[0]

                self._embeddings = _ProviderEmbeddings()
            except Exception as e:
                logger.warning(f"Failed to init embeddings: {e}")
                self._embeddings = None
        return self._embeddings

    def _ensure_store(self):
        """Lazy-init FAISS index."""
        if self._store is not None:
            return True
        try:
            from langchain_community.vectorstores import FAISS
            embeddings = self._get_embeddings()
            if embeddings is None:
                return False
            # Bootstrap with a seed document
            self._store = FAISS.from_texts(
                texts=[self._fallback_docs],
                embedding=embeddings,
                metadatas=[{"source": "seed", "type": "course_material"}],
            )
            self._initialized = True
            logger.info("FAISS vector store initialized successfully.")
            self._bootstrap_from_sqlite()
            return True
        except Exception as e:
            logger.warning(f"FAISS init failed (falling back to static docs): {e}")
            return False

    def _bootstrap_from_sqlite(self) -> None:
        """FAISS is in-memory and per-process — nothing indexes it on
        startup, so anything saved to SQLite by an earlier process (a prior
        run before a restart, ingestion done out-of-band, hitl.approve()
        from a different request) is durable but permanently unsearchable by
        rag_chatbot_node until re-ingested in the current process's
        lifetime. Runs once, right after the store itself is created, so a
        fresh process starts already caught up with whatever's confirmed in
        SQLite rather than only what it happens to ingest itself."""
        try:
            from .storage import get_db

            items = get_db().get_all_timeline()
            if items:
                self.index_timeline_items(items)
                logger.info(f"Bootstrapped FAISS with {len(items)} existing timeline item(s) from SQLite.")
        except Exception as e:
            logger.warning(f"FAISS bootstrap from SQLite failed (index stays seed-only): {e}")

    def add_documents(
        self,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """
        Add documents to the FAISS index.
        
        Returns number of documents successfully indexed.
        """
        if not self._ensure_store():
            return 0

        if not texts:
            return 0

        if metadatas is None:
            metadatas = [{"source": "dynamic"} for _ in texts]

        try:
            self._store.add_texts(texts=texts, metadatas=metadatas)
            logger.info(f"Indexed {len(texts)} documents into FAISS.")
            return len(texts)
        except Exception as e:
            logger.warning(f"Failed to add documents to FAISS: {e}")
            return 0

    def index_timeline_items(self, items: List[Dict[str, Any]]) -> int:
        """
        Index timeline items as searchable documents.
        
        Converts each timeline item into a text representation
        for semantic search.
        """
        if not items:
            return 0

        texts = []
        metadatas = []

        for item in items:
            # Build a rich text representation of the timeline item
            parts = []
            if item.get("category"):
                parts.append(f"[{item['category'].upper()}]")
            if item.get("title"):
                parts.append(item["title"])
            if item.get("description"):
                parts.append(item["description"])
            if item.get("due_date"):
                parts.append(f"Due: {item['due_date']}")
            if item.get("due_time"):
                parts.append(f"Time: {item['due_time']}")
            if item.get("priority"):
                parts.append(f"Priority: {item['priority']}")

            text = " | ".join(parts)
            if text.strip():
                texts.append(text)
                metadatas.append({
                    "source": "timeline",
                    "type": item.get("category", "other"),
                    "item_id": item.get("id", ""),
                    "due_date": item.get("due_date", ""),
                    "title": item.get("title", ""),
                    # For chat citations back to the original mail — see
                    # rag_chatbot_node's sources_cited population.
                    "source_platform": item.get("source_platform", ""),
                    "source_message_id": item.get("source_message_id", ""),
                })

        return self.add_documents(texts, metadatas)

    def similarity_search(self, query: str, k: int = 3) -> str:
        """
        Search the vector store for documents similar to the query.
        
        Returns a formatted string of retrieved documents for RAG injection.
        Falls back to static docs if FAISS is unavailable.
        """
        if not self._ensure_store():
            logger.info("FAISS unavailable, using fallback static docs.")
            return self._fallback_docs

        try:
            results = self._store.similarity_search_with_score(query, k=k)

            if not results:
                return self._fallback_docs

            retrieved_parts = []
            for i, (doc, score) in enumerate(results, 1):
                source = doc.metadata.get("source", "unknown")
                doc_type = doc.metadata.get("type", "general")
                retrieved_parts.append(
                    f"[Doc {i}] (source={source}, type={doc_type}, relevance={1-score:.2f})\n"
                    f"{doc.page_content}"
                )

            retrieved_text = "\n\n".join(retrieved_parts)
            logger.info(f"Retrieved {len(results)} documents for query: {query[:50]}...")
            return retrieved_text

        except Exception as e:
            logger.warning(f"FAISS search failed: {e}")
            return self._fallback_docs

    def similarity_search_with_metadata(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        """Same retrieval as similarity_search, but returns metadata instead
        of a formatted prompt string — for callers that need to cite sources
        (rag_chatbot_node's sources_cited/timeline_items_referenced) rather
        than inject retrieved text into a prompt. Empty list, not an
        exception or fallback text, when nothing is retrievable."""
        if not self._ensure_store():
            return []
        try:
            results = self._store.similarity_search_with_score(query, k=k)
            return [{"text": doc.page_content, **doc.metadata} for doc, _score in results]
        except Exception as e:
            logger.warning(f"FAISS metadata search failed: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════

_vector_store_instance: Optional[VectorStoreManager] = None


def get_vector_store() -> VectorStoreManager:
    """Get or create the singleton VectorStoreManager instance."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStoreManager()
    return _vector_store_instance
