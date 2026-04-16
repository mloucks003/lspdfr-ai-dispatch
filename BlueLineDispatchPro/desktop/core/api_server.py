"""
BlueLineDispatchPro — Local HTTP API Server
Flask server on localhost:7623 for FiveM companion integration.
"""
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from flask import Flask, request, jsonify
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logger.warning("Flask not available — API server disabled")


class APIServer:
    """
    Local HTTP API server. FiveM companion POSTs data here.
    Runs in a background daemon thread.
    """

    def __init__(self, settings: Dict,
                 on_plate: Optional[Callable] = None,
                 on_ped: Optional[Callable] = None,
                 on_call: Optional[Callable] = None,
                 on_unit: Optional[Callable] = None,
                 on_bolo: Optional[Callable] = None,
                 on_panic: Optional[Callable] = None,
                 on_ping: Optional[Callable] = None):
        self.settings = settings
        self.on_plate = on_plate
        self.on_ped = on_ped
        self.on_call = on_call
        self.on_unit = on_unit
        self.on_bolo = on_bolo
        self.on_panic = on_panic
        self.on_ping = on_ping
        self._server_thread: Optional[threading.Thread] = None
        self._app: Optional[object] = None

    @property
    def api_settings(self) -> Dict:
        return self.settings.get("api_server", {})

    @property
    def host(self) -> str:
        return self.api_settings.get("host", "127.0.0.1")

    @property
    def port(self) -> int:
        return int(self.api_settings.get("port", 7623))

    @property
    def api_key(self) -> str:
        return self.api_settings.get("api_key", "")

    def start(self) -> bool:
        if not FLASK_AVAILABLE:
            logger.error("Flask not installed. API server cannot start.")
            return False
        if not self.api_settings.get("enabled", True):
            logger.info("API server disabled in settings")
            return False

        self._app = self._create_app()
        self._server_thread = threading.Thread(
            target=self._run, daemon=True, name="APIServer"
        )
        self._server_thread.start()
        logger.info(f"API server started on http://{self.host}:{self.port}")
        return True

    def stop(self) -> None:
        # Flask dev server doesn't have a clean shutdown in thread mode
        # The daemon thread will die when the main process exits
        logger.info("API server stopping (daemon thread will exit with main process)")

    def _create_app(self) -> "Flask":
        app = Flask("BlueLineDispatchPro")
        app.config["JSON_SORT_KEYS"] = False
        CORS(app, origins=["null", "http://localhost", "http://127.0.0.1"])

        log = logging.getLogger("werkzeug")
        if not self.api_settings.get("log_requests", True):
            log.setLevel(logging.ERROR)

        @app.before_request
        def check_api_key():
            if self.api_key:
                key = request.headers.get("X-API-Key", "")
                if key != self.api_key:
                    return jsonify({"error": "Unauthorized"}), 401

        @app.route("/api/status", methods=["GET"])
        def status():
            return jsonify({
                "status": "online",
                "service": "BlueLineDispatchPro",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "port": self.port,
            })

        @app.route("/api/ping", methods=["POST"])
        def ping():
            data = self._parse_body()
            if self.on_ping:
                self.on_ping(data)
            return jsonify({"status": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})

        @app.route("/api/plate", methods=["POST"])
        def plate():
            data = self._parse_body()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            logger.info(f"[API] Plate data received: {data.get('plate', '?')}")
            if self.on_plate:
                self.on_plate(data)
            return jsonify({"status": "ok", "received": "plate"})

        @app.route("/api/ped", methods=["POST"])
        def ped():
            data = self._parse_body()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            name = f"{data.get('first_name','')} {data.get('last_name','')}".strip()
            logger.info(f"[API] Ped data received: {name}")
            if self.on_ped:
                self.on_ped(data)
            return jsonify({"status": "ok", "received": "ped"})

        @app.route("/api/call", methods=["POST"])
        def call():
            data = self._parse_body()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            logger.info(f"[API] New call: {data.get('type', '?')} at {data.get('location', '?')}")
            if self.on_call:
                self.on_call(data)
            return jsonify({"status": "ok", "received": "call"})

        @app.route("/api/call/<call_id>", methods=["PATCH"])
        def update_call(call_id: str):
            data = self._parse_body()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            data["call_id"] = call_id
            if self.on_call:
                self.on_call({"_update": True, **data})
            return jsonify({"status": "ok"})

        @app.route("/api/unit", methods=["POST"])
        def unit():
            data = self._parse_body()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            logger.info(f"[API] Unit update: {data.get('unit_id', '?')} → {data.get('status', '?')}")
            if self.on_unit:
                self.on_unit(data)
            return jsonify({"status": "ok", "received": "unit"})

        @app.route("/api/bolo", methods=["POST"])
        def bolo():
            data = self._parse_body()
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400
            logger.info(f"[API] BOLO received: {data.get('subject', '?')}")
            if self.on_bolo:
                self.on_bolo(data)
            return jsonify({"status": "ok", "received": "bolo"})

        @app.route("/api/panic", methods=["POST"])
        def panic():
            data = self._parse_body()
            logger.warning(f"[API] PANIC received from: {data.get('unit_id', 'UNKNOWN')}")
            if self.on_panic:
                self.on_panic(data or {})
            return jsonify({"status": "ok", "received": "panic"})

        @app.errorhandler(404)
        def not_found(e):
            return jsonify({"error": "Endpoint not found"}), 404

        @app.errorhandler(500)
        def internal_error(e):
            logger.error(f"API internal error: {e}")
            return jsonify({"error": "Internal server error"}), 500

        return app

    def _parse_body(self) -> Optional[Dict]:
        try:
            return request.get_json(force=True, silent=True) or {}
        except Exception:
            return {}

    def _run(self) -> None:
        try:
            import werkzeug
            self._app.run(
                host=self.host,
                port=self.port,
                debug=False,
                use_reloader=False,
                threaded=True,
            )
        except Exception as e:
            logger.error(f"API server error: {e}")
