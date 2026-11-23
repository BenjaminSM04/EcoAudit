"""Consulta y exportación de la bitácora administrativa."""

import csv
import io
import json
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import record, require_roles
from ..models import AuditLog, Role, User

router = APIRouter(prefix="/api", tags=["bitácora"])
_admin = require_roles(Role.admin)
CSV_LIMIT = 50_000


class AuditFilters(BaseModel):
    user_id: int | None = Field(default=None, gt=0)
    action: str | None = Field(default=None, max_length=64)
    desde: datetime | None = None
    hasta: datetime | None = None


class AuditPagination(AuditFilters):
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    action: str
    entity: str
    entity_id: int | None
    detail: dict
    created_at: datetime


class AuditPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditEntry]


def _filtered_query(filters: AuditFilters):
    query = select(AuditLog)
    for bound in (filters.desde, filters.hasta):
        if bound is not None and bound.utcoffset() is None:
            raise HTTPException(422, "Las fechas de la bitácora requieren zona horaria.")
    if filters.desde and filters.hasta and filters.desde > filters.hasta:
        raise HTTPException(422, "La fecha desde debe ser anterior o igual a hasta.")
    for value, column in (
        (filters.user_id, AuditLog.user_id),
        (filters.action, AuditLog.action),
    ):
        if value is not None:
            query = query.where(column == value)
    if filters.desde is not None:
        query = query.where(AuditLog.created_at >= filters.desde)
    if filters.hasta is not None:
        query = query.where(AuditLog.created_at <= filters.hasta)
    return query


def _newest_first(query):
    return query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


@router.get("/audit-log")
def audit_log(
    filters: Annotated[AuditPagination, Query()],
    db: Session = Depends(get_db),
    user: User = Depends(_admin),
) -> AuditPage:
    query = _filtered_query(filters)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(_newest_first(query).offset(filters.offset).limit(filters.limit))
    return AuditPage(
        total=total,
        limit=filters.limit,
        offset=filters.offset,
        items=[AuditEntry.model_validate(row) for row in rows],
    )


def _stream_csv(db: Session, query) -> Iterator[str]:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(AuditEntry.model_fields)
    with db.scalars(query.execution_options(yield_per=500)) as rows:
        for batch in rows.partitions():
            for item in batch:
                row = AuditEntry.model_validate(item).model_dump(mode="json")
                row["detail"] = json.dumps(row["detail"], ensure_ascii=False)
                writer.writerow(row.values())
            yield out.getvalue()
            out.seek(0)
            out.truncate()
    if out.tell():
        yield out.getvalue()


@router.get("/audit-log.csv")
def audit_log_csv(
    filters: Annotated[AuditFilters, Query()],
    db: Session = Depends(get_db),
    user: User = Depends(_admin),
) -> StreamingResponse:
    query = _filtered_query(filters)
    filtered = query.subquery()
    total, last_id = db.execute(select(func.count(), func.max(filtered.c.id))).one()
    query = _newest_first(query.where(AuditLog.id <= (last_id or 0))).limit(CSV_LIMIT)
    record(db, user, "audit_log_exported", "audit_log", count=min(total, CSV_LIMIT))
    db.commit()
    return StreamingResponse(
        _stream_csv(db, query),
        media_type="text/csv",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="bitacora.csv"',
            "X-Total-Count": str(total),
        },
    )
