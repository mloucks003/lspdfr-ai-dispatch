"""CAD Call data model."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from backend.models.common import CallNote, Location, PyObjectId
from backend.models.enums import CallStatus


class CADCall(BaseModel):
    """A Computer Aided Dispatch call record."""

    id: Optional[PyObjectId] = Field(None, alias="_id")
    call_number: Optional[str] = None
    type: str
    priority: int = Field(..., ge=1, le=3, description="1=high, 2=medium, 3=low")
    location: Location
    description: str
    suspect_description: Optional[str] = None
    assigned_units: List[str] = Field(default_factory=list)
    status: CallStatus = CallStatus.PENDING
    notes: List[CallNote] = Field(default_factory=list)
    disposition: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
