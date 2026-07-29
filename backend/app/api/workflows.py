from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from app.api.dependencies import get_workflow_service
from app.api.schemas import WorkflowRunRequest, WorkflowRunResponse
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _format_validation_error_details(errors: list[ErrorDetails]) -> list[dict[str, object]]:
	formatted_errors = []
	for error in errors:
		location = error.get("loc")
		field = ".".join(str(part) for part in location) if isinstance(location, tuple | list) else "input"
		formatted_errors.append(
			{
				"field": field,
				"message": str(error.get("msg") or "Invalid value."),
				"type": str(error.get("type") or "validation_error"),
			}
		)
	return formatted_errors


def _build_validation_error_detail(workflow_type: str, errors: list[ErrorDetails]) -> dict[str, object]:
	return {
		"message": f"Invalid input for workflow_type: {workflow_type}",
		"workflow_type": workflow_type,
		"errors": _format_validation_error_details(errors),
	}


@router.post("/run", response_model=WorkflowRunResponse)
async def run_workflow(
	payload: WorkflowRunRequest,
	service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> WorkflowRunResponse:
	return await _run_workflow_request(
		workflow_type=payload.workflow_type,
		session_id=payload.session_id,
		input_payload=payload.input,
		service=service,
	)


async def _run_workflow_request(
	*,
	workflow_type: str,
	session_id: str | None,
	input_payload: dict[str, object],
	service: WorkflowService,
) -> WorkflowRunResponse:
	workflow_type = workflow_type.strip()
	if workflow_type not in service.supported_workflow_types():
		raise HTTPException(
			status_code=400,
			detail={
				"message": f"Unsupported workflow_type: {workflow_type}",
				"supported_workflow_types": service.supported_workflow_types(),
			},
		)
	try:
		validated_input = service.validate_workflow_input(workflow_type, input_payload)
	except ValidationError as exc:
		raise HTTPException(
			status_code=422,
			detail=_build_validation_error_detail(workflow_type, exc.errors()),
		) from exc
	run_session_id = session_id or f"session-{uuid4().hex}"
	result = await service.run_workflow(
		workflow_type,
		session_id=run_session_id,
		**validated_input.model_dump(),
	)
	return WorkflowRunResponse.model_validate(result.to_dict())