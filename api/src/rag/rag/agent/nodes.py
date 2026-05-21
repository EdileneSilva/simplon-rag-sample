"""
Agent LangGraph — nœuds instrumentés pour l'observabilité.

Chaque nœud :
1. Mesure sa durée avec time.perf_counter().
2. Émet un log structuré JSON (sans PII).
3. Enregistre les métriques Prometheus correspondantes.

Règles RGPD :
- user_message, answer, retrieved_chunks.content ne sont JAMAIS loggés ni
  présents dans les labels de métriques.
"""

import json
import logging
import re
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_mistralai import ChatMistralAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.config.settings import get_settings
from rag.db.models.conversation import Conversation, Message
from rag.observability import (
    RAG_CHUNKS_RETRIEVED,
    RAG_ESCALATIONS_TOTAL,
    RAG_EVAL_SCORE,
    RAG_GUARD_ROUTE_DECISIONS_TOTAL,
    RAG_NODE_DURATION_SECONDS,
    RAG_RETRIES_TOTAL,
)
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
    content = content.strip()
    match = re.search(r"\{.*\}", content, re.DOTALL)
    return match.group(0) if match else content


def _get_llm(settings=None, model: str = "mistral-small-latest") -> ChatMistralAI:
    s = settings or get_settings()
    return ChatMistralAI(model=model, api_key=s.mistral_api_key)

# ---------------------------------------------------------------------------
# Nœuds
# ---------------------------------------------------------------------------

async def load_history(state: AgentState, db: AsyncSession) -> dict:
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
    t0 = time.perf_counter()

    settings = get_settings()
    llm = _get_llm(settings, model="mistral-small-latest")
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

    duration = time.perf_counter() - t0

    if not in_scope:
        # --- Métriques ---
        RAG_GUARD_ROUTE_DECISIONS_TOTAL.labels(
            decision="out_of_scope", category="out_of_scope"
        ).inc()
        RAG_NODE_DURATION_SECONDS.labels(node="guard_route").observe(duration)

        logger.info(
            "guard_route.decision",
            extra={
                "conversation_id": str(state["conversation_id"]),
                "node": "guard_route",
                "in_scope": False,
                "category": "out_of_scope",
                "needs_retrieval": False,
                "latency_ms": round(duration * 1000, 2),
            },
        )
        return {
            "in_scope": False,
            "needs_retrieval": False,
            "category": "out_of_scope",
            "answer": OUT_OF_SCOPE_RESPONSE.format(product_name=settings.product_name),
            "sources": [],
        }

    # --- Métriques ---
    RAG_GUARD_ROUTE_DECISIONS_TOTAL.labels(
        decision="in_scope", category=category or "unknown"
    ).inc()
    RAG_NODE_DURATION_SECONDS.labels(node="guard_route").observe(duration)

    logger.info(
        "guard_route.decision",
        extra={
            "conversation_id": str(state["conversation_id"]),
            "node": "guard_route",
            "in_scope": True,
            "category": category,
            "needs_retrieval": needs_retrieval,
            "latency_ms": round(duration * 1000, 2),
        },
    )
    return {"in_scope": True, "needs_retrieval": needs_retrieval, "category": category}


async def retrieve(state: AgentState, db: AsyncSession) -> dict:
    t0 = time.perf_counter()

    using_rewrite = bool(state.get("rewrite_suggestion"))
    chunks = await pgvector_retriever.similarity_search(
        state.get("rewrite_suggestion") or state["user_message"], db
    )

    duration = time.perf_counter() - t0

    # --- Métriques ---
    RAG_CHUNKS_RETRIEVED.observe(len(chunks))
    RAG_NODE_DURATION_SECONDS.labels(node="retrieve").observe(duration)

    logger.info(
        "retrieve.done",
        extra={
            "conversation_id": str(state["conversation_id"]),
            "node": "retrieve",
            "chunks_retrieved": len(chunks),
            "using_rewrite": using_rewrite,
            "latency_ms": round(duration * 1000, 2),
        },
    )
    return {"retrieved_chunks": chunks}


async def generate(state: AgentState) -> dict:
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
    duration = time.perf_counter() - t0

    # --- Métriques ---
    RAG_NODE_DURATION_SECONDS.labels(node="generate").observe(duration)

    logger.info(
        "generate.done",
        extra={
            "conversation_id": str(state["conversation_id"]),
            "node": "generate",
            "has_context": has_context,
            "sources_count": len(sources),
            "latency_ms": round(duration * 1000, 2),
        },
    )
    return {"answer": response.content, "sources": sources}


async def evaluate(state: AgentState) -> dict:
    t0 = time.perf_counter()
    settings = get_settings()
    llm = _get_llm(settings, model="mistral-small-latest")

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
    duration = time.perf_counter() - t0

    # --- Métriques ---
    RAG_EVAL_SCORE.observe(score)
    RAG_NODE_DURATION_SECONDS.labels(node="evaluate").observe(duration)
    if decision == "rewrite":
        RAG_RETRIES_TOTAL.inc()

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
            "latency_ms": round(duration * 1000, 2),
        },
    )
    return {
        "eval_score": score,
        "eval_decision": decision,
        "rewrite_suggestion": rewrite_suggestion,
        "retry_count": retry_count,
    }


async def escalate(state: AgentState) -> dict:
    settings = get_settings()

    # --- Métriques ---
    RAG_ESCALATIONS_TOTAL.inc()
    RAG_NODE_DURATION_SECONDS.labels(node="escalate").observe(0.0)

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