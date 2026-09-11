"""HTTP routes for health checks and artwork tasks."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from .config import settings
from .db import get_firestore_client

router = APIRouter()
logger = logging.getLogger(__name__)


class ArtworkTask(BaseModel):
    """Payload used to create an artwork task."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    client_name: str = Field(min_length=1, max_length=200)
    task_type: str = Field(min_length=1, max_length=100)
    status: str = Field(default="draft", min_length=1, max_length=50)


class ArtworkTaskResponse(ArtworkTask):
    """Artwork task returned by the API."""

    id: str
    created_at: datetime | None = None


@router.get("/health")
def health() -> dict[str, str]:
    """Return a basic service health response."""

    return {"status": "ok", "service": settings.app_name}


@router.post(
    "/api/v1/tasks",
    response_model=ArtworkTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(task: ArtworkTask) -> ArtworkTaskResponse:
    """Save an artwork task to Firestore and return its generated ID."""

    created_at = datetime.now(timezone.utc)
    document = task.model_dump()
    document["created_at"] = created_at

    try:
        document_reference = get_firestore_client().collection(
            settings.firestore_collection
        ).document()
        document_reference.set(document)
    except Exception as exc:
        logger.exception("Firestore create task failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore is unavailable.",
        ) from exc

    return ArtworkTaskResponse(
        id=document_reference.id,
        created_at=created_at,
        **task.model_dump(),
    )


@router.get("/api/v1/tasks", response_model=list[ArtworkTaskResponse])
def list_tasks() -> list[ArtworkTaskResponse]:
    """Stream all artwork task documents from Firestore."""

    try:
        documents = get_firestore_client().collection(
            settings.firestore_collection
        ).stream()
        tasks: list[ArtworkTaskResponse] = []
        for document in documents:
            data: dict[str, Any] = document.to_dict()
            tasks.append(
                ArtworkTaskResponse(
                    id=document.id,
                    title=data["title"],
                    client_name=data["client_name"],
                    task_type=data["task_type"],
                    status=data.get("status", "draft"),
                    created_at=data.get("created_at"),
                )
            )
        return tasks
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A stored artwork task has an invalid shape.",
        ) from exc
    except Exception as exc:
        logger.exception("Firestore list tasks failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore is unavailable.",
        ) from exc
