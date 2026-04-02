"""Shared enumerations for LSPDFR AI Dispatch data models."""

from enum import Enum


class CallStatus(str, Enum):
    """Status of a CAD call."""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    ON_SCENE = "on_scene"
    CLOSED = "closed"


class WarrantStatus(str, Enum):
    """Status of a warrant."""

    ACTIVE = "active"
    SERVED = "served"


class BOLOStatus(str, Enum):
    """Status of a BOLO."""

    ACTIVE = "active"
    CANCELLED = "cancelled"


class LicenseStatus(str, Enum):
    """License status for a person."""

    VALID = "valid"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    NONE_ = "none"


class AuditOperation(str, Enum):
    """Type of database write operation."""

    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
