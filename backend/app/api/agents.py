"""AI-эндпоинты (Weeks 7-8): анализ контракта, чат с агентами, генерация."""

import asyncio
import json
import logging
import time
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.contracts import get_visible_contract
from app.core.config import settings
from app.core.dependencies import get_current_user, get_upload_user
from app.core.permissions import require_permission
from app.db.base import async_session_factory, get_db
from app.db.models import AgentChatSession, AgentResult, Organization, User
from app.agents.chat import AGENT_PROMPTS, CHAT_MAX_TOKENS, agent_chat, build_agent_prompt
from app.agents.orchestrator import ContractAnalysisOrchestrator
from app.agents.response_standard import append_legal_standard, legal_basis_payload
from app.services import search as search_service
from app.services.ai_usage import enforce_ai_access, record_ai_usage
from app.utils.audit import log_action
from app.utils.document_parser import parse_file, pdf_needs_ocr
from app.utils.llm import (
    UsageCollector,
    collect_usage,
    extract_pdf_text,
    llm_text_stream,
    require_api_key,
)
from app.utils.upload_security import UploadSecurityError, secure_upload

router = APIRouter(prefix="/api", tags=["ai-agents"])
logger = logging.getLogger("app.ai_agents")
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


# ---------- Анализ контракта ----------

@router.post("/contracts/{contract_id}/analyze")
async def trigger_analysis(
    contract_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    """Полный AI-анализ: структура + закон + риски (+ комплаенс, если
    у организации заданы внутренние политики)."""
    require_api_key()
    await enforce_ai_access(db, user)
    return await _perform_contract_analysis(
        contract_id,
        user,
        db,
        ip_address=request.client.host if request.client else None,
    )


async def _perform_contract_analysis(
    contract_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    *,
    ip_address: str | None = None,
):
    contract = await get_visible_contract(contract_id, user, db)
    if not contract.content:
        raise HTTPException(
            status_code=400, detail="У контракта нет текста для анализа"
        )

    org = await db.get(Organization, user.organization_id)
    orchestrator = ContractAnalysisOrchestrator()
    with collect_usage() as usage:
        report = await orchestrator.run_analysis(
            str(contract.id),
            contract.content,
            compliance_policies=org.compliance_policies if org else None,
            db=db,
        )
    record_ai_usage(db, user, usage, endpoint="contract_analysis", agent="orchestrator")

    for agent_name, result in report["analysis"].items():
        db.add(
            AgentResult(
                contract_id=contract.id,
                agent_name=agent_name,
                result_type="analysis",
                result_data=result,
                execution_time_ms=report["timings_ms"].get(agent_name),
            )
        )

    contract.risk_score = report["analysis"]["risk_agent"].get("overall_score")
    if contract.status == "draft":
        contract.status = "analyzed"

    await log_action(
        db,
        action="contract_analyzed",
        user_id=user.id,
        resource_type="contract",
        resource_id=contract.id,
        changes={"risk_score": contract.risk_score},
        ip_address=ip_address,
    )
    await db.commit()
    await search_service.index_contract(contract)
    return report


@router.get("/contracts/{contract_id}/analysis")
async def get_analysis(
    contract_id: uuid.UUID,
    user: User = Depends(get_upload_user),
    db: AsyncSession = Depends(get_db),
):
    """Последние сохранённые результаты анализа по каждому агенту."""
    contract = await get_visible_contract(contract_id, user, db)
    result = await db.execute(
        select(AgentResult)
        .where(
            AgentResult.contract_id == contract.id,
            AgentResult.result_type == "analysis",
        )
        .order_by(AgentResult.created_at)
    )
    latest: dict[str, dict] = {}
    analyzed_at = None
    for row in result.scalars():
        latest[row.agent_name] = row.result_data
        analyzed_at = row.created_at
    return {
        "contract_id": str(contract.id),
        "analyzed_at": analyzed_at,
        "analysis": latest,
    }


# ---------- Чат с агентами ----------

class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=20_000)
    agent: str | None = Field(default=None, max_length=64)
    feedback: Literal["up", "down"] | None = None
    sources: list[dict] = Field(default_factory=list, max_length=10)


class ChatRequest(BaseModel):
    agent: str = "analyzer"
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    contract_id: uuid.UUID | None = None
    document_text: str | None = Field(default=None, max_length=100_000)
    document_name: str | None = Field(default=None, max_length=512)
    session_id: uuid.UUID | None = None


def _validate_chat_request(data: ChatRequest) -> None:
    require_api_key()
    if data.agent not in AGENT_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестный агент. Доступны: {sorted(AGENT_PROMPTS)}",
        )
    if not data.messages:
        raise HTTPException(status_code=400, detail="Пустая история сообщений")


async def _resolve_chat_context(
    data: ChatRequest, user: User, db: AsyncSession
) -> tuple[str | None, str | None]:
    """Контекст разговора: явный документ, контракт или прошлый контекст сессии."""
    existing_session: AgentChatSession | None = None
    if data.session_id is not None:
        existing_session = (
            await db.execute(
                select(AgentChatSession).where(
                    AgentChatSession.id == data.session_id,
                    AgentChatSession.user_id == user.id,
                    AgentChatSession.organization_id == user.organization_id,
                )
            )
        ).scalar_one_or_none()

    context_text = data.document_text
    context_label = data.document_name
    if data.contract_id is not None:
        contract = await get_visible_contract(data.contract_id, user, db)
        context_text = contract.content or ""
        context_label = contract.title
    elif context_text is None and existing_session is not None:
        if existing_session.contract_id is not None:
            contract = await get_visible_contract(existing_session.contract_id, user, db)
            context_text = contract.content or ""
            context_label = contract.title
        elif existing_session.document_text:
            context_text = existing_session.document_text
            context_label = existing_session.document_name
    return context_text, context_label


@router.post("/agents/chat")
async def chat_with_agent(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _validate_chat_request(data)
    await enforce_ai_access(db, user)
    context_text, context_label = await _resolve_chat_context(data, user, db)

    with collect_usage() as usage:
        chat_result = await agent_chat(
            data.agent,
            [m.model_dump() for m in data.messages],
            context_document=context_text,
            context_label=context_label,
            db=db,
        )
    if isinstance(chat_result, str):
        reply = chat_result
        verified_sources: list[dict] = []
    else:
        reply = chat_result.reply
        verified_sources = legal_basis_payload(chat_result.legal_sources)
    record_ai_usage(db, user, usage, endpoint="agent_chat", agent=data.agent)
    await _store_chat_session(db, user, data, reply, verified_sources)
    await db.commit()
    return {"reply": reply, "sources": verified_sources}


async def _store_chat_session(
    db: AsyncSession,
    user: User,
    data: ChatRequest,
    reply: str,
    verified_sources: list[dict],
) -> None:
    if data.session_id is None:
        return
    session = (
        await db.execute(
            select(AgentChatSession)
            .where(
                AgentChatSession.id == data.session_id,
                AgentChatSession.user_id == user.id,
                AgentChatSession.organization_id == user.organization_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if session is None:
        if user.organization_id is None:
            raise HTTPException(status_code=400, detail="Create an organization first")
        session = AgentChatSession(
            id=data.session_id,
            organization_id=user.organization_id,
            user_id=user.id,
            agent=data.agent,
            title="Новый чат",
            messages=[],
        )
        db.add(session)
    stored_messages = [m.model_dump() for m in data.messages]
    stored_messages.append(
        {
            "role": "assistant",
            "content": reply,
            "agent": data.agent,
            "sources": verified_sources,
        }
    )
    session.agent = data.agent
    session.messages = stored_messages[-100:]
    session.title = _chat_title(stored_messages)
    if data.contract_id is not None:
        session.contract_id = data.contract_id
        session.document_name = None
        session.document_text = None
    elif data.document_text is not None:
        session.contract_id = None
        session.document_name = data.document_name
        session.document_text = data.document_text


@router.post("/agents/chat/stream")
async def chat_with_agent_stream(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Потоковый чат (SSE): текст уходит юристу по мере генерации.

    События: {"type":"delta","text"} — кусок текста; {"type":"done","reply",
    "sources"} — финальный ответ после проверки цитат (заменяет черновой текст);
    {"type":"error","detail"}. Проверка источников выполняется по полному
    тексту, поэтому стрим показывает черновик, а финал приходит проверенным.
    """
    _validate_chat_request(data)
    await enforce_ai_access(db, user)
    context_text, context_label = await _resolve_chat_context(data, user, db)
    prompt = await build_agent_prompt(
        data.agent,
        [m.model_dump() for m in data.messages],
        context_document=context_text,
        context_label=context_label,
        db=db,
    )
    user_id = user.id

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_stream():
        parts: list[str] = []
        usage = UsageCollector()
        try:
            async for delta in llm_text_stream(
                system=prompt.system,
                messages=prompt.history,
                max_tokens=CHAT_MAX_TOKENS,
                usage=usage,
            ):
                parts.append(delta)
                yield _sse({"type": "delta", "text": delta})
            reply = append_legal_standard("".join(parts), prompt.legal_sources)
            verified_sources = legal_basis_payload(prompt.legal_sources)
            # Ответ уже отправляется клиенту — сохраняем отдельной сессией БД
            async with async_session_factory() as store_db:
                fresh_user = await store_db.get(User, user_id)
                if fresh_user is not None:
                    record_ai_usage(
                        store_db, fresh_user, usage, endpoint="agent_chat", agent=data.agent
                    )
                    await _store_chat_session(
                        store_db, fresh_user, data, reply, verified_sources
                    )
                    await store_db.commit()
            yield _sse({"type": "done", "reply": reply, "sources": verified_sources})
        except Exception as exc:  # ошибку доносим событием — HTTP уже 200
            yield _sse(
                {"type": "error", "detail": str(exc) or "Не удалось получить ответ агента"}
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chat_title(messages: list[dict]) -> str:
    first = next(
        (str(message.get("content", "")) for message in messages if message.get("role") == "user"),
        "Новый чат",
    )
    clean = " ".join(first.split())
    return f"{clean[:48]}..." if len(clean) > 48 else clean or "Новый чат"


# Фоновые задачи OCR-распознавания. Синхронный ответ не подходит: OCR скана
# занимает минуты, а cloudflare-туннель обрывает соединение на ~100-й секунде
# («Failed to fetch» у пользователя). Поэтому: мгновенный ответ с job_id +
# лёгкий поллинг статуса. Хранилище в памяти — процесс uvicorn один.
_PARSE_JOBS: dict[str, dict] = {}
_PARSE_JOB_TTL_SECONDS = 30 * 60


def _cleanup_parse_jobs() -> None:
    now = time.monotonic()
    for job_id in [
        job_id
        for job_id, job in _PARSE_JOBS.items()
        if now - job["created"] > _PARSE_JOB_TTL_SECONDS
    ]:
        _PARSE_JOBS.pop(job_id, None)


async def _run_ocr_job(
    job_id: str,
    user_id: uuid.UUID,
    data: bytes,
    filename: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    job = _PARSE_JOBS.get(job_id)
    try:
        with collect_usage() as usage:
            text = await extract_pdf_text(data, filename)
        # Запрос уже завершён — расход токенов пишем отдельной сессией
        async with session_factory() as db:
            job_user = await db.get(User, user_id)
            if job_user is not None:
                record_ai_usage(
                    db, job_user, usage, endpoint="pdf_ocr", agent="document_parser"
                )
                await db.commit()
        if job is not None:
            job.update(status="done", text=text, extraction_method="ocr")
    except Exception as exc:
        if job is not None:
            job.update(
                status="error",
                detail=str(exc) or "Не удалось распознать сканированный PDF",
            )


@router.post("/agents/parse-file")
async def parse_document_for_chat(
    file: UploadFile = File(...),
    user: User = Depends(get_upload_user),
    db: AsyncSession = Depends(get_db),
):
    """Извлечь текст из файла для вложения в чат (без сохранения в систему).

    Текстовые файлы отдаются сразу (status=done). Сканированные PDF уходят
    в фоновое OCR: возвращается status=processing + job_id для поллинга.
    """
    try:
        filename, data = await secure_upload(file)
        text = parse_file(filename, data)
    except UploadSecurityError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not pdf_needs_ocr(filename, text):
        return {
            "status": "done",
            "filename": filename,
            "text": text,
            "extraction_method": "text",
        }

    # Скан без текстового слоя: доступность ИИ проверяем сразу, чтобы отдать
    # понятную ошибку (503/429) синхронно, а не внутри фоновой задачи
    require_api_key()
    await enforce_ai_access(db, user)
    _cleanup_parse_jobs()
    job_id = uuid.uuid4().hex
    _PARSE_JOBS[job_id] = {
        "created": time.monotonic(),
        "user_id": str(user.id),
        "filename": filename,
        "status": "processing",
    }
    if db.bind is None:
        raise HTTPException(status_code=503, detail="База данных временно недоступна")
    session_factory = async_sessionmaker(db.bind, expire_on_commit=False)
    _spawn_background(
        _run_ocr_job(job_id, user.id, data, filename, session_factory)
    )
    return {"status": "processing", "job_id": job_id, "filename": filename}


@router.get("/agents/parse-file/jobs/{job_id}")
async def parse_document_job_status(
    job_id: str,
    user: User = Depends(get_upload_user),
):
    """Статус фонового распознавания. Отвечает мгновенно — таймауты не страшны."""
    _cleanup_parse_jobs()
    job = _PARSE_JOBS.get(job_id)
    if job is None or job.get("user_id") != str(user.id):
        raise HTTPException(
            status_code=404,
            detail="Задача распознавания не найдена (возможно, сервер перезапускался). Приложите файл ещё раз.",
        )
    if job["status"] == "done":
        return {
            "status": "done",
            "filename": job["filename"],
            "text": job["text"],
            "extraction_method": job["extraction_method"],
        }
    if job["status"] == "error":
        return {"status": "error", "detail": job["detail"]}
    return {"status": "processing"}


# ---------- Перевод контракта ----------

class TranslateRequest(BaseModel):
    target_lang: str = "uz"


@router.post("/contracts/{contract_id}/translate")
async def translate_contract(
    contract_id: uuid.UUID,
    data: TranslateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Юридический перевод контракта (Translation Agent, Phase 2)."""
    require_api_key()
    await enforce_ai_access(db, user)
    return await _perform_translation(contract_id, data.target_lang, user, db)


async def _perform_translation(
    contract_id: uuid.UUID,
    target_lang: str,
    user: User,
    db: AsyncSession,
):
    contract = await get_visible_contract(contract_id, user, db)
    if not contract.content:
        raise HTTPException(status_code=400, detail="У контракта нет текста")

    orchestrator = ContractAnalysisOrchestrator()
    try:
        with collect_usage() as usage:
            translated = await orchestrator.translation_agent.translate(
                contract.content, target_lang
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.add(
        AgentResult(
            contract_id=contract.id,
            agent_name="translation_agent",
            result_type=f"translation_{target_lang}",
            result_data={"target_lang": target_lang, "content": translated},
        )
    )
    record_ai_usage(db, user, usage, endpoint="contract_translation", agent="translator")
    await db.commit()
    return {"target_lang": target_lang, "content": translated}


# ---------- Генерация черновика ----------

class DraftRequest(BaseModel):
    contract_type: str
    requirements: dict


@router.post("/agents/draft")
async def generate_draft(
    data: DraftRequest,
    user: User = Depends(require_permission("create")),
    db: AsyncSession = Depends(get_db),
):
    """Сгенерировать текст договора по требованиям (Draft Agent)."""
    require_api_key()
    await enforce_ai_access(db, user)
    return await _perform_draft(data.contract_type, data.requirements, user, db)


async def _perform_draft(
    contract_type: str,
    requirements: dict,
    user: User,
    db: AsyncSession,
):
    orchestrator = ContractAnalysisOrchestrator()
    with collect_usage() as usage:
        content = await orchestrator.draft_agent.create_contract(
            contract_type, requirements
        )
    record_ai_usage(db, user, usage, endpoint="draft_generation", agent="draft")
    await db.commit()
    return {"content": content}


# ---------- Фоновые длительные AI-операции ----------

_AI_JOBS: dict[str, dict] = {}
_AI_JOB_TTL_SECONDS = 60 * 60


def _cleanup_ai_jobs() -> None:
    now = time.monotonic()
    for job_id in [
        key
        for key, job in _AI_JOBS.items()
        if now - job["created"] > _AI_JOB_TTL_SECONDS
    ]:
        _AI_JOBS.pop(job_id, None)


def _start_ai_job(
    user: User,
    operation: str,
    payload: dict,
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    _cleanup_ai_jobs()
    job_id = uuid.uuid4().hex
    _AI_JOBS[job_id] = {
        "created": time.monotonic(),
        "user_id": str(user.id),
        "operation": operation,
        "status": "processing",
    }
    _spawn_background(
        _run_ai_job(job_id, user.id, operation, payload, session_factory)
    )
    return job_id


async def _run_ai_job(
    job_id: str,
    user_id: uuid.UUID,
    operation: str,
    payload: dict,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    job = _AI_JOBS.get(job_id)
    try:
        async with session_factory() as db:
            user = await db.get(User, user_id)
            if user is None or not user.is_active:
                raise ValueError("Пользователь не найден или отключён")
            if operation == "analysis":
                result = await _perform_contract_analysis(
                    uuid.UUID(payload["contract_id"]),
                    user,
                    db,
                    ip_address=payload.get("ip_address"),
                )
            elif operation == "translation":
                result = await _perform_translation(
                    uuid.UUID(payload["contract_id"]),
                    payload["target_lang"],
                    user,
                    db,
                )
            elif operation == "draft":
                result = await _perform_draft(
                    payload["contract_type"],
                    payload["requirements"],
                    user,
                    db,
                )
            else:
                raise ValueError("Неизвестная AI-операция")
        if job is not None:
            job.update(status="done", result=result)
    except Exception as exc:
        logger.exception("Background AI job %s (%s) failed", job_id, operation)
        if job is not None:
            detail = getattr(exc, "detail", None) or str(exc) or "AI-операция завершилась с ошибкой"
            job.update(status="error", detail=str(detail)[:500])


@router.post("/contracts/{contract_id}/analyze/jobs")
async def start_analysis_job(
    contract_id: uuid.UUID,
    request: Request,
    user: User = Depends(require_permission("edit")),
    db: AsyncSession = Depends(get_db),
):
    require_api_key()
    await enforce_ai_access(db, user)
    contract = await get_visible_contract(contract_id, user, db)
    if not contract.content:
        raise HTTPException(status_code=400, detail="У контракта нет текста для анализа")
    if db.bind is None:
        raise HTTPException(status_code=503, detail="База данных временно недоступна")
    job_id = _start_ai_job(
        user,
        "analysis",
        {
            "contract_id": str(contract_id),
            "ip_address": request.client.host if request.client else None,
        },
        async_sessionmaker(db.bind, expire_on_commit=False),
    )
    return {"status": "processing", "job_id": job_id}


@router.post("/contracts/{contract_id}/translate/jobs")
async def start_translation_job(
    contract_id: uuid.UUID,
    data: TranslateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_api_key()
    await enforce_ai_access(db, user)
    contract = await get_visible_contract(contract_id, user, db)
    if not contract.content:
        raise HTTPException(status_code=400, detail="У контракта нет текста")
    if db.bind is None:
        raise HTTPException(status_code=503, detail="База данных временно недоступна")
    job_id = _start_ai_job(
        user,
        "translation",
        {"contract_id": str(contract_id), "target_lang": data.target_lang},
        async_sessionmaker(db.bind, expire_on_commit=False),
    )
    return {"status": "processing", "job_id": job_id}


@router.post("/agents/draft/jobs")
async def start_draft_job(
    data: DraftRequest,
    user: User = Depends(require_permission("create")),
    db: AsyncSession = Depends(get_db),
):
    require_api_key()
    await enforce_ai_access(db, user)
    if db.bind is None:
        raise HTTPException(status_code=503, detail="База данных временно недоступна")
    job_id = _start_ai_job(
        user,
        "draft",
        {"contract_type": data.contract_type, "requirements": data.requirements},
        async_sessionmaker(db.bind, expire_on_commit=False),
    )
    return {"status": "processing", "job_id": job_id}


@router.get("/agents/tasks/{job_id}")
async def ai_job_status(
    job_id: str,
    user: User = Depends(get_current_user),
):
    _cleanup_ai_jobs()
    job = _AI_JOBS.get(job_id)
    if job is None or job.get("user_id") != str(user.id):
        raise HTTPException(
            status_code=404,
            detail="AI-задача не найдена (возможно, сервер перезапускался). Запустите операцию ещё раз.",
        )
    if job["status"] == "done":
        return {"status": "done", "result": job["result"]}
    if job["status"] == "error":
        return {"status": "error", "detail": job["detail"]}
    return {"status": "processing", "operation": job["operation"]}
