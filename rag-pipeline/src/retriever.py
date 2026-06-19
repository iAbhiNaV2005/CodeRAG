"""
Retriever + LLM chain.

Embeds the user question, runs cosine similarity search against pgvector,
assembles a grounded prompt, and calls Gemini 1.5 Flash via LangChain.
Returns the answer with source citations.
"""

import logging
from dataclasses import dataclass, field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.config import get_settings
from src.embedder import embed_query
from src.storage import SearchResult, search_similar

logger = logging.getLogger(__name__)

# ── System prompt ────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert code assistant. Your job is to answer questions about a codebase using ONLY the provided code context.

Rules:
1. Base your answer ONLY on the code snippets provided below. Do not invent or assume code that isn't shown.
2. Always cite your sources: mention the file path and line range (e.g. `src/auth.py:10-45`) when referencing specific code.
3. If the provided context doesn't contain enough information to fully answer the question, say so explicitly and explain what additional code you would need to see.
4. Use code blocks with the appropriate language identifier when showing code.
5. Be concise but thorough. Explain what the code does and why, not just what it looks like.
6. If multiple files are relevant, explain how they connect to each other."""


@dataclass
class Source:
    """A source citation from the retrieved code chunks."""

    file_path: str
    start_line: int
    end_line: int
    snippet: str
    language: str
    similarity: float


@dataclass
class Answer:
    """The complete answer from the RAG pipeline."""

    text: str
    sources: list[Source] = field(default_factory=list)
    repo_id: str = ""
    question: str = ""


def _build_context_block(results: list[SearchResult]) -> str:
    """Format retrieved chunks into a context block for the prompt."""
    if not results:
        return "No relevant code chunks were found."

    blocks = []
    for i, result in enumerate(results, 1):
        block = (
            f"[Source {i}: {result.file_path}:{result.start_line}-{result.end_line}]"
            f" (similarity: {result.similarity:.3f})\n"
            f"```{result.language}\n"
            f"{result.content}\n"
            f"```"
        )
        blocks.append(block)

    return "\n\n".join(blocks)


def _build_chat_history_messages(
    chat_history: list[dict[str, str]] | None,
) -> list[HumanMessage | AIMessage]:
    """Convert chat history dicts to LangChain message objects."""
    if not chat_history:
        return []

    messages = []
    for entry in chat_history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    return messages


def query(
    question: str,
    repo_id: str,
    chat_history: list[dict[str, str]] | None = None,
    top_k: int | None = None,
) -> Answer:
    """
    Full RAG query: embed question → search pgvector → assemble prompt → call Gemini.

    Args:
        question: The user's natural-language question about the codebase.
        repo_id: Which repository to search.
        chat_history: Optional list of prior conversation turns for multi-turn support.
                      Each entry: {"role": "user"|"assistant", "content": "..."}
        top_k: Number of chunks to retrieve (defaults to settings.retrieval_top_k).

    Returns:
        Answer object with the LLM response text and source citations.
    """
    settings = get_settings()

    # Step 1: Embed the question
    logger.info("Embedding question: %s", question[:80])
    query_embedding = embed_query(question)

    # Step 2: Search pgvector
    logger.info("Searching pgvector (repo: %s, top_k: %s)", repo_id, top_k or settings.retrieval_top_k)
    results = search_similar(query_embedding, repo_id, top_k)

    if not results:
        return Answer(
            text="I couldn't find any relevant code in this repository for your question. "
                 "Try rephrasing your question or make sure the repository has been fully ingested.",
            sources=[],
            repo_id=repo_id,
            question=question,
        )

    # Step 3: Build the prompt
    context_block = _build_context_block(results)

    user_message_content = (
        f"## Code Context\n\n{context_block}\n\n"
        f"## Question\n\n{question}"
    )

    # Build message list
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # Add chat history for multi-turn conversations
    if chat_history:
        history_messages = _build_chat_history_messages(chat_history)
        messages.extend(history_messages)

    messages.append(HumanMessage(content=user_message_content))

    # Step 4: Call Gemini 1.5 Flash
    logger.info("Calling Gemini 2.5 Flash...")
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.google_api_key,
        temperature=0.1,  # Low temp for factual code answers
        max_output_tokens=2048,
    )

    response = llm.invoke(messages)
    answer_text = response.content

    # Step 5: Build source citations
    sources = [
        Source(
            file_path=r.file_path,
            start_line=r.start_line,
            end_line=r.end_line,
            snippet=r.content[:200] + ("..." if len(r.content) > 200 else ""),
            language=r.language,
            similarity=r.similarity,
        )
        for r in results
    ]

    logger.info("Answer generated (%d chars, %d sources)", len(answer_text), len(sources))

    return Answer(
        text=answer_text,
        sources=sources,
        repo_id=repo_id,
        question=question,
    )
