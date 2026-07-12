"""Debug/search endpoints for the local legal knowledge base."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.base import get_db
from app.db.models import LegalArticle, LegalDocument, User
from app.services.legal_search import search_legal_articles

router = APIRouter(prefix="/api/legal", tags=["legal-knowledge"])


@router.get("/search")
async def search_law(
    q: str = Query(..., min_length=2),
    limit: int = Query(8, ge=1, le=25),
    language: str = "ru",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="Create an organization first")
    items = await search_legal_articles(db, q=q, limit=limit, language=language)
    return {"total": len(items), "items": items}


@router.get("/documents")
async def list_legal_documents(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="Create an organization first")
    rows = (
        await db.execute(
            select(LegalDocument, func.count(LegalArticle.id))
            .outerjoin(LegalArticle)
            .group_by(LegalDocument.id)
            .order_by(LegalDocument.title)
        )
    ).all()
    return {
        "items": [
            {
                "id": str(document.id),
                "source": document.source,
                "source_id": document.source_id,
                "title": document.title,
                "doc_type": document.doc_type,
                "language": document.language,
                "url": document.url,
                "current_revision_date": (
                    document.current_revision_date.isoformat()
                    if document.current_revision_date
                    else None
                ),
                "articles_count": articles_count,
            }
            for document, articles_count in rows
        ]
    }
