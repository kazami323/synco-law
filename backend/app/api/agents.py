"""AI-эндпоинты (Weeks 7-8): анализ контракта, чат с агентами, генерация."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.contracts import get_visible_contract
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.permissions import require_permission
from app.db.base import get_db
from app.db.models import AgentResult, Organization, User
from app.agents.chat import AGENT_PROMPTS, agent_chat
from app.agents.orchestrator import ContractAnalysisOrchestrator
from app.services import search as search_service
from app.utils.audit import log_action
from app.utils.document_parser import parse_file
from app.utils.llm import require_api_key

router = APIRouter(prefix="/api", tags=["ai-agents"])


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
    contract = await get_visible_contract(contract_id, user, db)
    if not contract.content:
        raise HTTPException(
            status_code=400, detail="У контракта нет текста для анализа"
        )

    org = await db.get(Organization, user.organization_id)
    orchestrator = ContractAnalysisOrchestrator(settings.LEX_UZ_API_KEY)
    report = await orchestrator.run_analysis(
        str(contract.id),
        contract.content,
        compliance_policies=org.compliance_policies if org else None,
    )

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
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await search_service.index_contract(contract)
    return report


@router.get("/contracts/{contract_id}/analysis")
async def get_analysis(
    contract_id: uuid.UUID,
    user: User = Depends(get_current_user),
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
    role: str
    content: str


class ChatRequest(BaseModel):
    agent: str = "analyzer"
    messages: list[ChatMessage]
    contract_id: uuid.UUID | None = None
    document_text: str | None = None
    document_name: str | None = None


@router.post("/agents/chat")
async def chat_with_agent(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_api_key()
    if data.agent not in AGENT_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестный агент. Доступны: {sorted(AGENT_PROMPTS)}",
        )
    if not data.messages:
        raise HTTPException(status_code=400, detail="Пустая история сообщений")

    context_text = data.document_text
    context_label = data.document_name
    if data.contract_id is not None:
        contract = await get_visible_contract(data.contract_id, user, db)
        context_text = contract.content or ""
        context_label = contract.title

    reply = await agent_chat(
        data.agent,
        [m.model_dump() for m in data.messages],
        context_document=context_text,
        context_label=context_label,
    )
    return {"reply": reply}


@router.post("/agents/parse-file")
async def parse_document_for_chat(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Извлечь текст из файла для вложения в чат (без сохранения в систему)."""
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Файл больше 20 МБ")
    try:
        text = parse_file(file.filename or "document", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"filename": file.filename, "text": text}


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
    contract = await get_visible_contract(contract_id, user, db)
    if not contract.content:
        raise HTTPException(status_code=400, detail="У контракта нет текста")

    orchestrator = ContractAnalysisOrchestrator()
    try:
        translated = await orchestrator.translation_agent.translate(
            contract.content, data.target_lang
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db.add(
        AgentResult(
            contract_id=contract.id,
            agent_name="translation_agent",
            result_type=f"translation_{data.target_lang}",
            result_data={"target_lang": data.target_lang, "content": translated},
        )
    )
    await db.commit()
    return {"target_lang": data.target_lang, "content": translated}


# ---------- Генерация черновика ----------

class DraftRequest(BaseModel):
    contract_type: str
    requirements: dict


@router.post("/agents/draft")
async def generate_draft(
    data: DraftRequest,
    user: User = Depends(require_permission("create")),
):
    """Сгенерировать текст договора по требованиям (Draft Agent)."""
    require_api_key()
    orchestrator = ContractAnalysisOrchestrator()
    content = await orchestrator.draft_agent.create_contract(
        data.contract_type, data.requirements
    )
    return {"content": content}
