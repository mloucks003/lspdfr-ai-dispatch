"""Person / Ped data model."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.models.common import PhysicalDescription, PriorOffense, PyObjectId
from backend.models.enums import LicenseStatus


class Person(BaseModel):
    """A person / ped record in the database."""

    id: Optional[PyObjectId] = Field(None, alias="_id")
    name: str
    date_of_birth: str = Field(..., description="Format: YYYY-MM-DD")
    physical_description: PhysicalDescription
    prior_offenses: List[PriorOffense] = Field(default_factory=list)
    active_warrants: List[PyObjectId] = Field(
        default_factory=list, description="ObjectId refs to warrants collection"
    )
    license_status: LicenseStatus = LicenseStatus.VALID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}
