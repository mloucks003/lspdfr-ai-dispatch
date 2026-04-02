"""Data models package — Pydantic v2 models for all MongoDB collections."""

from backend.models.audit_log import AuditLogEntry
from backend.models.bolo import BOLO
from backend.models.cad_call import CADCall
from backend.models.citation import Citation
from backend.models.common import (
    CallNote,
    Coordinates,
    Location,
    PhysicalDescription,
    PriorOffense,
    PyObjectId,
)
from backend.models.enums import (
    AuditOperation,
    BOLOStatus,
    CallStatus,
    LicenseStatus,
    WarrantStatus,
)
from backend.models.person import Person
from backend.models.vehicle import Vehicle
from backend.models.warrant import Warrant

__all__ = [
    # Enums
    "AuditOperation",
    "BOLOStatus",
    "CallStatus",
    "LicenseStatus",
    "WarrantStatus",
    # Nested / common models
    "CallNote",
    "Coordinates",
    "Location",
    "PhysicalDescription",
    "PriorOffense",
    "PyObjectId",
    # Collection models
    "AuditLogEntry",
    "BOLO",
    "CADCall",
    "Citation",
    "Person",
    "Vehicle",
    "Warrant",
]
