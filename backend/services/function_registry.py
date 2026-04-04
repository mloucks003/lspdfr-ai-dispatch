"""Function calling registry and dispatcher for OpenAI Realtime API.

Defines tool schemas for each dispatch function and routes invocations
to the corresponding backend service.

Requirements: 3.3, 4.4, 6.4, 15.2, 15.5
"""

import json
import logging
from typing import Any, Dict, List

from backend.services.bolo_service import BOLOService
from backend.services.name_check import NameCheckService
from backend.services.officer_status import OfficerStatusService
from backend.services.plate_check import PlateCheckService
from backend.services.warrant_service import WarrantService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling schema)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "name": "plate_check",
        "description": "Look up a vehicle by license plate number. Returns the vehicle's make, model, color, registered owner name, registration status, insurance status, and any flags (stolen, expired registration, BOLO, etc). The data comes from the LSPD database.",
        "parameters": {
            "type": "object",
            "properties": {
                "plate": {"type": "string", "description": "The license plate number to look up."},
            },
            "required": ["plate"],
        },
    },
    {
        "type": "function",
        "name": "name_check",
        "description": "Look up a person by name. Returns name, DOB, physical description, priors, warrants, and license status.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The person's name to look up."},
            },
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "warrant_check",
        "description": "Check for active warrants for a person by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The person's name to check warrants for."},
            },
            "required": ["name"],
        },
    },
    {
        "type": "function",
        "name": "update_officer_status",
        "description": "Update an officer's status using a 10-code.",
        "parameters": {
            "type": "object",
            "properties": {
                "callsign": {"type": "string", "description": "The officer's unit callsign."},
                "status_code": {"type": "string", "description": "A valid 10-code (10-76, 10-97, 10-98, 10-8, 10-7)."},
            },
            "required": ["callsign", "status_code"],
        },
    },
    {
        "type": "function",
        "name": "request_backup",
        "description": "Request backup at a location. Creates a high-priority call.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "Street or landmark where backup is needed."},
                "details": {"type": "string", "description": "Additional details about the situation."},
            },
            "required": ["location"],
        },
    },
    {
        "type": "function",
        "name": "create_bolo",
        "description": "Create a Be On the Lookout (BOLO) alert.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Description of the BOLO."},
                "suspect_desc": {"type": "string", "description": "Suspect physical description."},
                "vehicle_desc": {"type": "string", "description": "Vehicle description."},
            },
            "required": ["description"],
        },
    },
    {
        "type": "function",
        "name": "assign_call",
        "description": "Assign an officer to an active CAD call.",
        "parameters": {
            "type": "object",
            "properties": {
                "call_id": {"type": "string", "description": "The CAD call ID to assign."},
                "callsign": {"type": "string", "description": "The officer's unit callsign."},
            },
            "required": ["call_id", "callsign"],
        },
    },
]


class FunctionRegistry:
    """Maps OpenAI function call names to backend service methods.

    Accepts all required services as constructor dependencies.
    """

    def __init__(
        self,
        plate_check_service: PlateCheckService,
        name_check_service: NameCheckService,
        warrant_service: WarrantService,
        officer_status_service: OfficerStatusService,
        bolo_service: BOLOService,
        default_callsign: str = "1-Adam-12",
    ) -> None:
        self._plate = plate_check_service
        self._name = name_check_service
        self._warrant = warrant_service
        self._officer = officer_status_service
        self._bolo = bolo_service
        self._default_callsign = default_callsign

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Return the list of tool definitions for OpenAI registration."""
        return list(TOOL_DEFINITIONS)

    async def dispatch(self, function_name: str, arguments: Dict[str, Any]) -> Any:
        """Route a function call to the correct service method.

        Args:
            function_name: The name of the function invoked by OpenAI.
            arguments: The parsed arguments dict from the function call.

        Returns:
            The result from the corresponding service method.

        Raises:
            ValueError: If *function_name* is not recognised.
        """
        logger.info("Dispatching function call: %s(%s)", function_name, arguments)

        if function_name == "plate_check":
            return await self._plate.check_plate(arguments["plate"])

        if function_name == "name_check":
            return await self._name.check_name(arguments["name"])

        if function_name == "warrant_check":
            return await self._warrant.check_warrants(arguments["name"])

        if function_name == "update_officer_status":
            return await self._officer.update_status(
                arguments["callsign"],
                arguments["status_code"],
            )

        if function_name == "request_backup":
            location = {"street": arguments["location"]}
            details = arguments.get("details", "Backup requested")
            return await self._officer.request_backup(location, details)

        if function_name == "create_bolo":
            return await self._bolo.create_bolo(
                description=arguments["description"],
                issuing_officer=self._default_callsign,
                suspect_description=arguments.get("suspect_desc"),
                vehicle_description=arguments.get("vehicle_desc"),
            )

        if function_name == "assign_call":
            return await self._officer.assign_call(
                arguments["call_id"],
                arguments["callsign"],
            )

        raise ValueError(f"Unknown function: {function_name!r}")
