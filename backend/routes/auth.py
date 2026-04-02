"""API key authentication dependency for REST endpoints.

Requirements: 13.5
"""

from fastapi import Header, HTTPException, status

from backend.config import settings


async def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """FastAPI dependency that validates the API key from request headers.

    Raises 401 Unauthorized if the key is missing or does not match.
    Returns the validated key on success.
    """
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
