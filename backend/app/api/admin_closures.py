"""`POST /admin/labs/{lab_id}/closures` (US-7)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db import get_session
from app.models import User
from app.schemas.admin import ClosureCreated, CreateClosureRequest
from app.services import closures as closures_service
from app.services.common import get_active_lab_or_404

router = APIRouter(tags=["admin"])


def _close(session: Session, lab_id: int, raw_body: bytes) -> ClosureCreated:
    # Contract order: 404 lab_not_found, then 422 validation_error, then the date checks.
    lab = get_active_lab_or_404(session, lab_id)
    body = closures_service.parse_request(raw_body)
    return closures_service.close_lab(session, lab, body.date)


@router.post(
    "/admin/labs/{lab_id}/closures",
    response_model=ClosureCreated,
    status_code=201,
    operation_id="adminCreateClosure",
    # The body is read by hand (see `parse_request`); this keeps it in the OpenAPI schema.
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": CreateClosureRequest.model_json_schema()}},
        }
    },
)
async def create_closure(
    lab_id: int,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    _admin: Annotated[User, Depends(require_admin)],
) -> ClosureCreated:
    raw_body = await request.body()
    return await run_in_threadpool(_close, session, lab_id, raw_body)
