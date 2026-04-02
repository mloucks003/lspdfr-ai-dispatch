"""LSPDFR AI Dispatch — FastAPI application entry point.

Instantiates all services, wires them together, and starts the
OpenAI Realtime client in the lifespan handler.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.config import settings
from backend.services.bolo_service import BOLOService
from backend.services.call_manager import CallManager
from backend.services.criminal_history import CriminalHistoryService
from backend.services import DatabaseService
from backend.services.function_registry import FunctionRegistry
from backend.services.game_state import GameStateService
from backend.services.name_check import NameCheckService
from backend.services.officer_status import OfficerStatusService
from backend.services.openai_client import OpenAIRealtimeClient
from backend.services.plate_check import PlateCheckService
from backend.services.system_prompt import SystemPromptBuilder
from backend.services.warrant_service import WarrantService
from backend.ws.hub import WebSocketHub

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Core singletons
# ---------------------------------------------------------------------------
db_service = DatabaseService()
ws_hub = WebSocketHub()

# ---------------------------------------------------------------------------
# Lookup / domain services
# ---------------------------------------------------------------------------
game_state_service = GameStateService(db=db_service)
call_manager = CallManager(db=db_service, hub=ws_hub)
officer_status_service = OfficerStatusService(db=db_service, hub=ws_hub)
plate_check_service = PlateCheckService(db=db_service)
name_check_service = NameCheckService(db=db_service)
warrant_service = WarrantService(db=db_service)
bolo_service = BOLOService(db=db_service, hub=ws_hub)
criminal_history_service = CriminalHistoryService(db=db_service)

# ---------------------------------------------------------------------------
# OpenAI integration
# ---------------------------------------------------------------------------
function_registry = FunctionRegistry(
    plate_check_service=plate_check_service,
    name_check_service=name_check_service,
    warrant_service=warrant_service,
    officer_status_service=officer_status_service,
    bolo_service=bolo_service,
    default_callsign=settings.default_callsign,
)
system_prompt_builder = SystemPromptBuilder()
openai_client = OpenAIRealtimeClient(
    api_key=settings.openai_api_key,
    hub=ws_hub,
    function_registry=function_registry,
    prompt_builder=system_prompt_builder,
    callsign=settings.default_callsign,
)

# Background task handle for the OpenAI client
_openai_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start services on startup, tear down on shutdown."""
    global _openai_task

    await db_service.start()

    # Start the OpenAI Realtime client in the background (Req 15.1)
    if settings.openai_api_key:
        _openai_task = asyncio.create_task(openai_client.start())
        logger.info("OpenAI Realtime client started in background")

    yield

    # Shutdown
    if _openai_task is not None:
        await openai_client.disconnect()
        _openai_task.cancel()
        try:
            await _openai_task
        except asyncio.CancelledError:
            pass

    await db_service.stop()


app = FastAPI(
    title="LSPDFR AI Dispatch",
    description="AI-powered police dispatch backend for LSPDFR",
    version="0.1.0",
    lifespan=lifespan,
)

# Register routers (imported after app/db_service to avoid circular imports)
from backend.routes.cad_static import router as cad_router  # noqa: E402
from backend.routes.calls import router as calls_router  # noqa: E402
from backend.routes.citations import router as citations_router  # noqa: E402
from backend.routes.persons import router as persons_router  # noqa: E402
from backend.routes.vehicles import router as vehicles_router  # noqa: E402
from backend.routes.warrants import router as warrants_router  # noqa: E402
from backend.ws.endpoints import router as ws_router  # noqa: E402

app.include_router(calls_router)
app.include_router(citations_router)
app.include_router(persons_router)
app.include_router(vehicles_router)
app.include_router(warrants_router)
app.include_router(ws_router)
app.include_router(cad_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
