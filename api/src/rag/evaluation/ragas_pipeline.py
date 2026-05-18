from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from rag.rag.agent.graph import build_graph


@dataclass
class EvaluationSample:
    question: str
    ground_truth: str


@dataclass
class EvaluationResult:
    faithfulness: float | None
    answer_relevancy: float | None
    context_recall: float | None
    raw: dict


async def run_evaluation(
    samples: list[EvaluationSample],
    db: AsyncSession,
) -> EvaluationResult:
    """Run a Ragas evaluation over a set of question/ground-truth pairs.

    For each sample the full agent graph is invoked to get an answer and contexts.
    """
    graph = build_graph(db)
    questions, answers, contexts, ground_truths = [], [], [], []

    for sample in samples:
        from rag.db.models.conversation import Conversation

        conversation = Conversation()
        db.add(conversation)
        await db.flush()

        state = await graph.ainvoke(
            {
                "conversation_id": str(conversation.id),
                "user_message": sample.question,
                "messages": [],
                "retrieved_chunks": [],
                "answer": "",
                "sources": [],
                "needs_retrieval": False,
            }
        )

        questions.append(sample.question)
        answers.append(state["answer"])
        contexts.append([c["content"] for c in state.get("retrieved_chunks", [])] or [""])
        ground_truths.append(sample.ground_truth)

    # Lazy imports to keep ragas off the FastAPI startup path
    from datasets import Dataset  # noqa: PLC0415
    from langchain_ollama import ChatOllama, OllamaEmbeddings  # noqa: PLC0415
    from ragas import evaluate  # noqa: PLC0415
    from ragas.llms import LangchainLLMWrapper  # noqa: PLC0415
    from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: PLC0415
    from ragas.metrics import answer_relevancy, context_recall, faithfulness  # noqa: PLC0415

    from rag.config.settings import get_settings  # noqa: PLC0415

    settings = get_settings()
    judge_llm = LangchainLLMWrapper(
        ChatOllama(
            model=settings.ollama_chat_model,
            base_url=settings.ollama_base_url,
        )
    )
    judge_embed = LangchainEmbeddingsWrapper(
        OllamaEmbeddings(
            model=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
        )
    )

    dataset = Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_recall],
        llm=judge_llm,
        embeddings=judge_embed,
    )
    scores = result.to_pandas().mean(numeric_only=True).to_dict()

    return EvaluationResult(
        faithfulness=scores.get("faithfulness"),
        answer_relevancy=scores.get("answer_relevancy"),
        context_recall=scores.get("context_recall"),
        raw=scores,
    )
