"""BOLO (Be On the Lookout) data model."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.common import PyObjectId
from backend.models.enums import BOLOStatus


class BOLO(BaseModel):
    """A BOLO record."""

    id: Optional[PyObjectId] = Field(None, alias="_id")
    description: str
    suspect_description: Optional[str] = None
    vehicle_description: Optional[str] = None
    issuing_officer: str
    status: BOLOStatus = BOLOStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
