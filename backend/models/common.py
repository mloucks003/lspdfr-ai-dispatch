"""Shared/nested sub-models and custom types used across multiple collections."""

from datetime import datetime
from typing import Annotated, Any, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer


def _validate_object_id(v: Any) -> ObjectId:
    """Accept str or ObjectId, return ObjectId."""
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str) and ObjectId.is_valid(v):
        return ObjectId(v)
    raise ValueError(f"Invalid ObjectId: {v}")


PyObjectId = Annotated[
    ObjectId,
    BeforeValidator(_validate_object_id),
    PlainSerializer(lambda v: str(v), return_type=str),
]
"""Custom type that accepts str or ObjectId and serialises to str for JSON."""


class Coordinates(BaseModel):
    """3D coordinates in the GTA V world."""

    x: float
    y: float
    z: float


class Location(BaseModel):
    """Location with street name, optional landmark, and coordinates."""

    street: str
    landmark: Optional[str] = None
    coordinates: Optional[Coordinates] = None


class CallNote(BaseModel):
    """A timestamped note on a CAD call."""

    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    author: str


class PhysicalDescription(BaseModel):
    """Physical description of a person/ped."""

    gender: str
    race: str
    height: str
    weight: str
    hair_color: str
    distinguishing_marks: Optional[str] = None


class PriorOffense(BaseModel):
    """A prior offense entry on a person record."""

    offense: str
    date: str
    disposition: str
