"""
Chat router -- handles Q&A with SSE streaming responses.

POST /chat -> Stream answer tokens via Server-Sent Events
"""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from src.api.models import ChatRequest
from src.config import get_settings
from src.embedder import embed_query
from src.storage import search_similar
from src.dynamo.repos import get_repo
from src.dynamo.sessions import get_or_create_session, append_chat_message, get_chat_history
from src.retriever import SYSTEM_PROMPT, _build_context_block

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


async def _stream_answer(
    question: str,
    repo_id: str,
    session_id: str,
    user_id: str,
) -> AsyncGenerator[dict, None]:
    """
    Generator that yields SSE events:
      - {"type": "session", "session_id": "..."}     (first event)
      - {"type": "token",   "content": "..."}        (streamed tokens)
      - {"type": "sources", "sources": [...]}        (after answer completes)
      - {"type": "done"}                              (final event)
    """
    settings = get_settings()

    # Get or create session
    session = get_or_create_session(session_id, repo_id, user_id)
    actual_session_id = session["session_id"]

    # Send session ID as first event
    yield {"event": "message", "data": json.dumps({
        "type": "session",
        "session_id": actual_session_id,
    })}

    # Step 1: Embed the question
    query_embedding = embed_query(question)

    # Step 2: Search pgvector
    results = search_similar(query_embedding, repo_id)

    if not results:
        yield {"event": "message", "data": json.dumps({
            "type": "token",
            "content": "I couldn't find any relevant code in this repository for your question.",
        })}
        yield {"event": "message", "data": json.dumps({"type": "done"})}
        return

    # Step 3: Build prompt with context + chat history
    context_block = _build_context_block(results)
    user_message_content = f"## Code Context\n\n{context_block}\n\n## Question\n\n{question}"

    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # Add chat history for multi-turn
    chat_history = get_chat_history(actual_session_id)
    for entry in chat_history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_message_content))

    # Step 4: Stream from Gemini
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.google_api_key,
        temperature=0.1,
        max_output_tokens=2048,
        streaming=True,
    )

    full_answer = ""

    try:
        async for chunk in llm.astream(messages):
            token = chunk.content
            if token:
                full_answer += token
                yield {"event": "message", "data": json.dumps({
                    "type": "token",
                    "content": token,
                })}
    except Exception as e:
        logger.error("LLM streaming error: %s", e)
        yield {"event": "message", "data": json.dumps({
            "type": "error",
            "content": f"LLM error: {str(e)[:200]}",
        })}
        yield {"event": "message", "data": json.dumps({"type": "done"})}
        return

    # Step 5: Send source citations
    sources = [
        {
            "file_path": r.file_path,
            "start_line": r.start_line,
            "end_line": r.end_line,
            "language": r.language,
            "snippet": r.content[:300],
            "similarity": round(r.similarity, 4),
        }
        for r in results
    ]

    yield {"event": "message", "data": json.dumps({
        "type": "sources",
        "sources": sources,
    })}

    # Step 6: Persist chat history
    append_chat_message(actual_session_id, "user", question)
    append_chat_message(actual_session_id, "assistant", full_answer)

    # Final event
    yield {"event": "message", "data": json.dumps({"type": "done"})}

    logger.info(
        "Chat complete: session=%s, answer_len=%d, sources=%d",
        actual_session_id, len(full_answer), len(sources),
    )


@router.post("")
async def chat(request: ChatRequest):
    """
    Ask a question about an ingested codebase.

    Returns a Server-Sent Event stream with:
    1. Session ID (first event)
    2. Answer tokens (streamed as they arrive)
    3. Source citations (after answer completes)
    4. Done signal (final event)
    """
    # Validate repo exists and is READY
    repo = get_repo(request.repo_id)
    if not repo:
        raise HTTPException(
            status_code=404,
            detail=f"Repository {request.repo_id} not found. Ingest it first via POST /ingest.",
        )

    if repo.get("status") != "READY":
        raise HTTPException(
            status_code=400,
            detail=f"Repository is not ready (status: {repo.get('status')}). Wait for ingestion to complete.",
        )

    return EventSourceResponse(
        _stream_answer(
            question=request.question,
            repo_id=request.repo_id,
            session_id=request.session_id,
            user_id=request.user_id,
        )
    )
