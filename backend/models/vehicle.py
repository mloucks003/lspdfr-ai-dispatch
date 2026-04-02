"""Vehicle data model."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.models.common import PyObjectId


class Vehicle(BaseModel):
    """A vehicle record in the database."""

    id: Optional[PyObjectId] = Field(None, alias="_id")
    plate: str
    make: str
    model: str
    color: str
    registered_owner: str = Field(
        ..., description="Reference to persons.name"
    )
    flags: List[str] = Field(
        default_factory=list,
        description="e.g. stolen, bolo, expired_registration",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
