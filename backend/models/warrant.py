"""Warrant data model."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.common import PyObjectId
from backend.models.enums import WarrantStatus


class Warrant(BaseModel):
    """A warrant record."""

    id: Optional[PyObjectId] = Field(None, alias="_id")
    person_name: str
    person_id: Optional[PyObjectId] = Field(
        None, description="ObjectId ref to persons collection"
    )
    charge: str
    issuing_authority: str
    date_issued: datetime
    status: WarrantStatus = WarrantStatus.ACTIVE
    date_served: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
