"""Audit log data model."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from backend.models.common import PyObjectId
from backend.models.enums import AuditOperation


class AuditLogEntry(BaseModel):
    """An audit log entry for database write operations."""

    id: Optional[PyObjectId] = Field(None, alias="_id")
    collection: str
    operation: AuditOperation
    document_id: PyObjectId
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
