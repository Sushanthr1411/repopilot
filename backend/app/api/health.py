from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="repopilot-ai")


@router.get("/v1/health", response_model=HealthResponse)
def v1_health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="repopilot-ai")
