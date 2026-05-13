"""
Agent LangGraph — nœuds instrumentés pour l'observabilité.

Règles RGPD appliquées :
- user_message, answer, retrieved_chunks.content ne sont JAMAIS loggés.
- Seuls les champs catégoriels, métriques et identifiants non-nominatifs
  (conversation_id, request_id via ContextVar, latency_ms) sont émis.
"""

import json
import logging
import re
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.config.settings import get_settings
from rag.db.models.conversation import Conversation, Message
from rag.rag.agent.prompts import (
    ESCALATION_RESPONSE,
    EVALUATOR_PROMPT,
    GUARD_ROUTE_PROMPT,
    OUT_OF_SCOPE_RESPONSE,
    RAG_SYSTEM_PROMPT,
    RAG_USER_PROMPT,
    SYSTEM_PROMPT,
)
from rag.rag.agent.state import AgentState
from rag.rag.retriever import pgvector_retriever

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _extract_json(content: str) -> str:
    """Strip markdown code fences and extract the first JSON object from LLM output."""
    content = content.strip()
    match = re.search(r"\{.*\}", content, re.DOTALL)
    return match.group(0) if match else content


def _get_llm(settings=None, model: str | None = None) -> ChatOllama:
    s = settings or get_settings()
    return ChatOllama(
        model=model or s.ollama_chat_model,
        base_url=s.ollama_base_url,
    )


# ---------------------------------------------------------------------------
# Nœuds du graphe
# ---------------------------------------------------------------------------

async def load_history(state: AgentState, db: AsyncSession) -> dict:
    """Load previous messages for this conversation from the DB."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == state["conversation_id"])
        .order_by(Message.created_at, Message.id)
    )
    db_messages = result.scalars().all()

    settings = get_settings()
    lc_messages: list = [
        SystemMessage(content=SYSTEM_PROMPT.format(product_name=settings.product_name))
    ]

    for msg in db_messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        else:
            lc_messages.append(AIMessage(content=msg.content))

    lc_messages.append(HumanMessage(content=state["user_message"]))
    return {"messages": lc_messages}


async def guard_route(state: AgentState) -> dict:
    """Single LLM call that decides scope and retrieval routing simultaneously.

    Returns:
        - in_scope=False + answer: short-circuits to save_turn (out-of-scope rejection)
        - in_scope=True + needs_retrieval=True: pipeline continues to retrieve
        - in_scope=True + needs_retrieval=False: pipeline continues to generate

    Fails open (in_scope=True, needs_retrieval=True) on any JSON parsing error
    to avoid false negatives.
    """
    t0 = time.perf_counter()

    settings = get_settings()
    llm = _get_llm(settings, model=settings.ollama_small_chat_model)
    prompt = GUARD_ROUTE_PROMPT.format(
        product_name=settings.product_name,
        user_message=state["user_message"],
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(_extract_json(response.content))
        in_scope = bool(data.get("in_scope", True))
        needs_retrieval = bool(data.get("needs_retrieval", True))
        category = str(data.get("category", ""))
    except (json.JSONDecodeError, ValueError):
        in_scope = True
        needs_retrieval = True
        category = ""

    latency_ms = (time.perf_counter() - t0) * 1000

    if not in_scope:
        logger.info(
            "guard_route.decision",
            extra={
                "conversation_id": str(state["conversation_id"]),
                "node": "guard_route",
                "in_scope": False,
                "category": "out_of_scope",
                "needs_retrieval": False,
                "latency_ms": round(latency_ms, 2),
            },
        )
        return {
            "in_scope": False,
            "needs_retrieval": False,
            "category": "out_of_scope",
            "answer": OUT_OF_SCOPE_RESPONSE.format(product_name=settings.product_name),
            "sources": [],
        }

    logger.info(
        "guard_route.decision",
        extra={
            "conversation_id": str(state["conversation_id"]),
            "node": "guard_route",
            "in_scope": True,
            "category": category,
            "needs_retrieval": needs_retrieval,
            "latency_ms": round(latency_ms, 2),
        },
    )
    return {"in_scope": True, "needs_retrieval": needs_retrieval, "category": category}


async def retrieve(state: AgentState, db: AsyncSession) -> dict:
    """Retrieve relevant chunks from pgvector.

    Uses rewrite_suggestion as the search query when available (rewrite path),
    otherwise falls back to the original user_message.
    """
    t0 = time.perf_counter()

    # Pas de log de la requête (contenu utilisateur) — RGPD
    using_rewrite = bool(state.get("rewrite_suggestion"))
    chunks = await pgvector_retriever.similarity_search(
        state.get("rewrite_suggestion") or state["user_message"], db
    )

    latency_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "retrieve.done",
        extra={
            "conversation_id": str(state["conversation_id"]),
            "node": "retrieve",
            "chunks_retrieved": len(chunks),
            "using_rewrite": using_rewrite,
            "latency_ms": round(latency_ms, 2),
        },
    )
    return {"retrieved_chunks": chunks}


async def generate(state: AgentState) -> dict:
    """Generate an answer using the local Ollama chat model, with optional retrieved context.

    The previous turns of the conversation are reused as structured messages
    (HumanMessage / AIMessage) rather than flattened into the system prompt,
    so the LLM keeps a clear turn-by-turn structure and prompt caching stays
    effective.

    The generated AIMessage is intentionally NOT appended to ``state["messages"]``:
    on a rewrite loop, a failed first answer would otherwise pollute the history
    fed to the second generation pass.
    """
    t0 = time.perf_counter()
    llm = _get_llm()

    history_msgs = state["messages"][1:-1]
    has_context = bool(state.get("retrieved_chunks"))

    if has_context:
        context = "\n\n---\n\n".join(
            f"[{c['filename']} chunk {c['chunk_index']}]\n{c['content']}"
            for c in state["retrieved_chunks"]
        )
        system_content = RAG_SYSTEM_PROMPT.format(
            product_name=get_settings().product_name,
            context=context,
        )
        user_content = RAG_USER_PROMPT.format(
            question=state["user_message"],
            category=state.get("category", ""),
        )
        messages_to_send = [
            SystemMessage(content=system_content),
            *history_msgs,
            HumanMessage(content=user_content),
        ]
        sources = [c["chunk_id"] for c in state["retrieved_chunks"]]
    else:
        messages_to_send = state["messages"]
        sources = []

    response = await llm.ainvoke(messages_to_send)

    latency_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "generate.done",
        extra={
            "conversation_id": str(state["conversation_id"]),
            "node": "generate",
            "has_context": has_context,
            "sources_count": len(sources),
            "latency_ms": round(latency_ms, 2),
        },
    )
    return {
        "answer": response.content,
        "sources": sources,
    }


async def evaluate(state: AgentState) -> dict:
    """Evaluate the quality of the generated answer and decide routing.

    Scores 0-10 across relevance, completeness, grounding, and clarity.
    - score >= 7 → "answer": send to user
    - score 4-6  → "rewrite": retry retrieval with a reformulated query
    - score < 4  → "escalate": hand off to human support

    Increments retry_count each call. If retry_count reaches 2, forces escalation
    regardless of score to prevent infinite loops.
    Fails open ("answer") on any JSON parsing error.
    """
    t0 = time.perf_counter()
    settings = get_settings()
    llm = _get_llm(settings, model=settings.ollama_small_chat_model)

    context_summary = "\n".join(
        f"- [{c['filename']}]: {c['content'][:100]}..."
        for c in (state.get("retrieved_chunks") or [])
    ) or "Aucun contexte récupéré."

    prompt = EVALUATOR_PROMPT.format(
        question=state["user_message"],
        context_summary=context_summary,
        answer=state.get("answer", ""),
    )
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        data = json.loads(_extract_json(response.content))
        score = float(data.get("score", 10))
        decision = str(data.get("decision", "answer"))
        rewrite_suggestion = str(data.get("rewrite_suggestion", ""))
    except (json.JSONDecodeError, ValueError):
        score = 10.0
        decision = "answer"
        rewrite_suggestion = ""

    retry_count = state.get("retry_count", 0) + 1
    latency_ms = (time.perf_counter() - t0) * 1000

    log_level = logging.WARNING if decision in ("rewrite", "escalate") else logging.INFO
    logger.log(
        log_level,
        "evaluate.decision",
        extra={
            "conversation_id": str(state["conversation_id"]),
            "node": "evaluate",
            "score": round(score, 2),
            "decision": decision,
            "retry_count": retry_count,
            "latency_ms": round(latency_ms, 2),
        },
    )
    return {
        "eval_score": score,
        "eval_decision": decision,
        "rewrite_suggestion": rewrite_suggestion,
        "retry_count": retry_count,
    }


async def escalate(state: AgentState) -> dict:
    """Set a human-escalation answer when the evaluator cannot find a satisfactory response."""
    settings = get_settings()
    logger.warning(
        "escalate.triggered",
        extra={
            "conversation_id": str(state["conversation_id"]),
            "node": "escalate",
            "retry_count": state.get("retry_count", 0),
        },
    )
    return {
        "answer": ESCALATION_RESPONSE.format(
            product_name=settings.product_name,
            question=state["user_message"],
        ),
        "sources": [],
    }


async def save_turn(state: AgentState, db: AsyncSession) -> dict:
    """Persist user message and assistant answer to the DB."""
    user_msg = Message(
        conversation_id=state["conversation_id"],
        role="user",
        content=state["user_message"],
    )
    assistant_msg = Message(
        conversation_id=state["conversation_id"],
        role="assistant",
        content=state["answer"],
        sources=state.get("sources"),
    )
    db.add_all([user_msg, assistant_msg])

    # Update conversation.updated_at
    result = await db.execute(
        select(Conversation).where(Conversation.id == state["conversation_id"])
    )
    conversation = result.scalar_one_or_none()
    if conversation:
        from sqlalchemy import func
        conversation.metadata_ = {**conversation.metadata_, "last_updated": str(func.now())}

    await db.commit()

    logger.info(
        "save_turn.done",
        extra={
            "conversation_id": str(state["conversation_id"]),
            "node": "save_turn",
            "eval_score": state.get("eval_score"),
            "eval_decision": state.get("eval_decision"),
        },
    )
    return {}