"""Citation data model."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from backend.models.common import PyObjectId


class Citation(BaseModel):
    """A citation / ticket record."""

    id: Optional[PyObjectId] = Field(None, alias="_id")
    person_name: str
    person_id: Optional[PyObjectId] = Field(
        None, description="ObjectId ref to persons collection"
    )
    violation_type: str
    location: str
    date: datetime
    officer_callsign: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
