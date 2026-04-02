# Implementation Plan: LSPDFR AI Dispatch

## Overview

This plan implements the LSPDFR AI Dispatch system across four components: a Python backend (FastAPI + MongoDB), a Python dispatch radio app, a C# LSPDFR plugin, and a React/TypeScript CAD frontend. Tasks are ordered so each step builds on the previous, starting with shared data models and backend core, then layering on each component, and finishing with integration wiring.

## Tasks

- [x] 1. Set up project structure and shared data models
  - [x] 1.1 Create backend project skeleton with FastAPI, Motor (async MongoDB driver), and WebSocket support
    - Initialize Python project with `pyproject.toml` or `requirements.txt`
    - Install FastAPI, uvicorn, motor, pydantic, websockets
    - Create directory structure: `backend/`, `backend/models/`, `backend/services/`, `backend/routes/`, `backend/ws/`
    - _Requirements: 14.1_

  - [x] 1.2 Define Pydantic data models for all MongoDB collections
    - Create models for `CADCall`, `Person`, `Vehicle`, `Citation`, `Warrant`, `BOLO`, `AuditLogEntry`
    - Include all fields from the design document data models
    - Add validation (priority 1-3, status enums, required fields)
    - _Requirements: 5.1, 9.1, 14.1_

  - [x] 1.3 Create MongoDB database service with connection management and index creation
    - Implement `DatabaseService` class with Motor async client
    - On startup, verify connection and create collections/indexes as defined in design (compound index on calls status+priority, text index on persons name, unique index on vehicles plate, etc.)
    - Implement queue-and-retry logic for writes when MongoDB is unavailable (retry every 5s)
    - _Requirements: 14.3, 14.4_

  - [ ]* 1.4 Write property tests for database write queue (Property 30)
    - **Property 30: Backend write queue on MongoDB failure**
    - Generate write operation sequences with simulated MongoDB failure, verify all queued and executed on restore
    - **Validates: Requirements 14.4**

  - [x] 1.5 Implement audit logging for all database writes
    - Create middleware/decorator that logs every insert, update, delete to the `audit_log` collection
    - Each entry: collection name, operation type, document ID, timestamp, details
    - _Requirements: 14.5_

  - [ ]* 1.6 Write property test for audit logging (Property 31)
    - **Property 31: Audit log for all writes**
    - Generate random write operations, verify audit log entries created with correct fields
    - **Validates: Requirements 14.5**

- [x] 2. Checkpoint — Ensure data models and database layer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implement backend CRUD REST API endpoints
  - [x] 3.1 Implement REST endpoints for calls collection
    - `GET /api/calls` — list active calls (sorted by priority)
    - `GET /api/calls/:id` — get call details
    - `PUT /api/calls/:id` — update call notes/disposition
    - _Requirements: 10.1, 10.4, 10.5, 14.2_

  - [x] 3.2 Implement REST endpoints for persons and vehicles collections
    - `GET /api/persons?q=` — search persons by name or DOB
    - `GET /api/vehicles?q=` — search vehicles by plate, make, or model
    - _Requirements: 11.1, 11.2, 11.3, 14.2_

  - [x] 3.3 Implement REST endpoints for citations, warrants, and BOLOs
    - `POST /api/citations` — create citation, link to person record
    - `GET /api/warrants?active=true` — list active warrants with filtering
    - `POST /api/warrants` — create warrant, flag person record
    - `PUT /api/warrants/:id/serve` — mark warrant served
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 14.2_

  - [ ]* 3.4 Write property tests for CRUD round trips (Property 29)
    - **Property 29: CRUD round trip for all collections**
    - Generate random entities for each collection, create via REST then read back, verify equivalence
    - **Validates: Requirements 14.2**

  - [ ]* 3.5 Write property tests for citation and warrant management (Properties 24, 25, 26, 27)
    - **Property 24: Citation creation links to person record**
    - **Property 25: Warrant creation flags person record**
    - **Property 26: Warrant filtering**
    - **Property 27: Warrant served status update**
    - **Validates: Requirements 12.3, 12.4, 12.5, 12.6**

  - [ ]* 3.6 Write property test for call notes (Property 22)
    - **Property 22: Call notes update round trip**
    - Generate random calls and notes, add note, retrieve, verify note present with timestamp and author
    - **Validates: Requirements 10.5**

- [x] 4. Implement backend WebSocket hub and authentication
  - [x] 4.1 Create WebSocket hub managing connections for radio, plugin, and CAD clients
    - Implement `WebSocketHub` class with connection registration for `/ws/radio`, `/ws/plugin`, `/ws/cad`
    - Implement broadcast to all connected clients and targeted send
    - Handle client disconnect: log disconnection, queue pending updates, accept reconnection
    - _Requirements: 13.1, 13.3, 13.4_

  - [x] 4.2 Implement API key authentication for WebSocket and REST connections
    - Validate shared API key on WebSocket handshake (reject invalid keys immediately)
    - Validate API key in REST request headers
    - _Requirements: 13.5_

  - [ ]* 4.3 Write property tests for WebSocket authentication (Property 28)
    - **Property 28: WebSocket authentication rejects invalid keys**
    - Generate random API keys (valid and invalid), verify accept/reject behavior
    - **Validates: Requirements 13.5**

  - [ ]* 4.4 Write property tests for broadcast and reconnection (Properties 8, 34)
    - **Property 8: Backend broadcasts events to all connected clients**
    - **Property 34: Backend reconnection preserves pending updates**
    - **Validates: Requirements 4.3, 5.3, 13.4**

- [x] 5. Checkpoint — Ensure REST API and WebSocket hub tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement backend call management and dispatch logic
  - [x] 6.1 Implement CallManager for creating CAD calls from 911 events
    - Convert 911 call events to CAD calls with priority (1-3), call type, location, suspect description, status "pending"
    - Auto-increment call numbers
    - Broadcast new calls to radio and CAD via WebSocket hub
    - _Requirements: 5.1, 5.3, 8.3_

  - [ ]* 6.2 Write property tests for call generation (Properties 9, 18)
    - **Property 9: Generated CAD calls contain all required fields**
    - **Property 18: 911 event to CAD call conversion**
    - **Validates: Requirements 5.1, 8.3, 10.1**

  - [x] 6.3 Implement call assignment and officer status tracking
    - Assign officer to call: add callsign to `assigned_units`, set officer status to 10-76
    - Handle status updates for 10-76, 10-97, 10-98, 10-8, 10-7
    - Persist status in MongoDB, broadcast changes to CAD within 1 second
    - _Requirements: 4.1, 4.3, 5.6_

  - [ ]* 6.4 Write property tests for call assignment and officer status (Properties 7, 11)
    - **Property 7: Officer status update persistence**
    - **Property 11: Call assignment updates both call and officer status**
    - **Validates: Requirements 4.1, 5.6**

  - [x] 6.5 Implement backup request handler
    - Create high-priority (1) CAD call at officer's current location
    - Broadcast to all connected units
    - _Requirements: 6.1_

  - [ ]* 6.6 Write property test for backup requests (Property 12)
    - **Property 12: Backup request creates high-priority call at location**
    - **Validates: Requirements 6.1**

  - [x] 6.7 Implement BOLO creation and broadcast
    - Create BOLO record with status "active", persist in MongoDB
    - Broadcast BOLO alert to CAD via WebSocket
    - _Requirements: 6.2_

  - [ ]* 6.8 Write property test for BOLO creation (Property 13)
    - **Property 13: BOLO creation persistence**
    - **Validates: Requirements 6.2**

  - [x] 6.9 Implement warrant check query
    - Query person database for active warrants by name
    - Return all active warrants or empty result
    - _Requirements: 6.3_

  - [ ]* 6.10 Write property test for warrant check (Property 14)
    - **Property 14: Warrant check returns active warrants**
    - **Validates: Requirements 6.3**

- [x] 7. Implement backend database lookup services (plate check, name check, criminal history)
  - [x] 7.1 Implement plate check service
    - Query vehicles collection by plate, return make, model, color, registered owner, flags
    - Return "no record on file" response when plate not found
    - _Requirements: 3.1, 3.4_

  - [ ]* 7.2 Write property test for plate check (Property 5)
    - **Property 5: Plate check returns complete vehicle record**
    - **Validates: Requirements 3.1, 11.5**

  - [x] 7.3 Implement name check service
    - Query persons collection by name, return full record (name, DOB, description, priors, warrants, license status)
    - Return "no record on file" response when name not found
    - _Requirements: 3.2, 3.4, 9.4_

  - [ ]* 7.4 Write property test for name check (Property 6)
    - **Property 6: Name check returns complete person record**
    - **Validates: Requirements 3.2, 9.1, 9.4, 11.4**

  - [x] 7.5 Implement criminal history generation for new peds
    - When a ped has no existing record, generate randomized criminal history: DOB, license status (valid/suspended/revoked/none), prior offenses
    - Persist generated record so subsequent queries return consistent data
    - _Requirements: 9.3, 9.5_

  - [ ]* 7.6 Write property tests for criminal history (Properties 19, 20)
    - **Property 19: Criminal history generation completeness**
    - **Property 20: Criminal history persistence consistency (round trip)**
    - **Validates: Requirements 9.3, 9.5**

  - [x] 7.7 Implement upsert logic for game state records (peds and vehicles)
    - Upsert ped/vehicle data from plugin so database stays current
    - Ensure idempotence: upserting same data twice results in one record
    - _Requirements: 11.6_

  - [ ]* 7.8 Write property test for upsert idempotence (Property 23)
    - **Property 23: Upsert idempotence for game state records**
    - **Validates: Requirements 11.6**

- [x] 8. Checkpoint — Ensure backend business logic tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement OpenAI Realtime API integration
  - [x] 9.1 Create OpenAI Realtime API WebSocket client
    - Establish WebSocket connection to OpenAI using configured API key
    - Forward audio from radio to OpenAI in required format
    - Forward audio responses from OpenAI back to radio
    - _Requirements: 15.1, 15.3, 15.4_

  - [x] 9.2 Implement function calling registry and dispatcher
    - Register function definitions: `plate_check`, `name_check`, `warrant_check`, `update_officer_status`, `request_backup`, `create_bolo`, `assign_call`
    - When OpenAI invokes a function, dispatch to the corresponding backend service and return result
    - _Requirements: 3.3, 4.4, 6.4, 15.2, 15.5_

  - [ ]* 9.3 Write property test for function call dispatch (Property 32)
    - **Property 32: Function call dispatch executes correct operation**
    - **Validates: Requirements 15.5**

  - [x] 9.4 Build system prompt with 10-code protocol and GTA V awareness
    - Construct prompt instructing AI to use 10-codes, radio brevity, professional dispatcher tone
    - Include GTA V location awareness directives
    - Include officer callsign context
    - _Requirements: 2.3, 15.6_

  - [ ]* 9.5 Write property test for system prompt (Property 4)
    - **Property 4: System prompt contains required protocol elements**
    - **Validates: Requirements 2.3, 15.6**

  - [x] 9.6 Implement exponential backoff reconnection for OpenAI connection
    - On disconnect, retry with backoff: min(2^N, 60) seconds
    - _Requirements: 15.7_

  - [ ]* 9.7 Write property test for exponential backoff (Property 33)
    - **Property 33: Exponential backoff calculation**
    - **Validates: Requirements 15.7**

- [x] 10. Checkpoint — Ensure OpenAI integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement Dispatch Radio application (Python)
  - [x] 11.1 Create dispatch radio project skeleton
    - Initialize Python project with PyAudio, websockets dependencies
    - Create directory structure: `dispatch_radio/`, modules for audio capture, playback, websocket client, session manager
    - _Requirements: 1.1_

  - [x] 11.2 Implement AudioCapture with continuous mic input and wake word detection
    - Continuous microphone capture using PyAudio
    - Wake word ("dispatch") detection via keyword spotting
    - Transition from passive listening to active command processing within 500ms
    - Handle missing microphone: display error, retry every 5 seconds
    - _Requirements: 1.1, 1.2, 1.5_

  - [ ]* 11.3 Write property test for wake word state transition (Property 1)
    - **Property 1: Wake word triggers state transition**
    - **Validates: Requirements 1.2**

  - [x] 11.4 Implement SessionManager with silence timeout
    - Track active/passive listening state
    - End active session after configurable silence duration (default 2s)
    - _Requirements: 1.4_

  - [ ]* 11.5 Write property test for silence timeout (Property 2)
    - **Property 2: Silence timeout ends active session**
    - **Validates: Requirements 1.4**

  - [x] 11.6 Implement AudioPlayback with squelch effect pipeline
    - Output device management
    - Squelch effect: click-on → static → voice → click-off
    - Play AI dispatcher responses through configured output device
    - _Requirements: 2.1, 2.2_

  - [ ]* 11.7 Write property test for squelch effect (Property 3)
    - **Property 3: Squelch effect wraps audio**
    - **Validates: Requirements 2.2**

  - [x] 11.8 Implement WebSocket client for radio-backend communication
    - Connect to backend `/ws/radio` endpoint with API key auth
    - Send audio chunks (base64 PCM) and status updates
    - Receive audio responses, call announcements, status acknowledgments
    - Reconnection logic (10s interval)
    - _Requirements: 1.3, 2.1, 2.4, 2.5, 5.4_

- [x] 12. Implement LSPDFR Plugin (C#)
  - [x] 12.1 Create C# plugin project skeleton
    - Set up RagePluginHook project with references
    - Create class structure: `GameStateReader`, `LocationResolver`, `CrimeEventDetector`, `WebSocketTransport`
    - _Requirements: 7.1_

  - [x] 12.2 Implement GameStateReader and LocationResolver
    - Poll GTA V APIs for nearby ped names, vehicle plates/models/colors
    - Read wanted level of target peds
    - Convert coordinates to GTA V street names using native functions
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 12.3 Implement CrimeEventDetector for 911 call generation
    - Monitor game events for crimes in progress
    - Generate 911 call payloads with crime type, location, involved ped descriptions, caller description
    - _Requirements: 8.1, 8.4_

  - [ ]* 12.4 Write property test for 911 call field completeness (Property 17)
    - **Property 17: 911 call event contains all required fields**
    - **Validates: Requirements 8.1, 8.4**

  - [x] 12.5 Implement WebSocketTransport with rate limiting and buffering
    - Connect to backend `/ws/plugin` endpoint with API key auth
    - Send game state updates and 911 call events
    - Rate limit to max 1 update/sec
    - Buffer updates on disconnect, transmit in order on reconnect
    - _Requirements: 7.4, 7.5, 7.6_

  - [ ]* 12.6 Write property tests for rate limiting and message buffer (Properties 15, 16)
    - **Property 15: Plugin message buffer on disconnect**
    - **Property 16: Plugin rate limiting**
    - **Validates: Requirements 7.5, 7.6**

- [x] 13. Checkpoint — Ensure dispatch radio and plugin tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement CAD System (React/TypeScript)
  - [x] 14.1 Create React project skeleton with WebSocket provider
    - Initialize React project with TypeScript
    - Create `WebSocketProvider` context for real-time updates from backend `/ws/cad`
    - Define TypeScript interfaces matching backend data models
    - _Requirements: 10.2, 13.1_

  - [x] 14.2 Implement CallBoard component
    - Display active calls table with columns: call number, type, priority, location, assigned units, status
    - Sort by priority (ascending: 1 first)
    - Color-code by priority: red (1), yellow (2), green (3)
    - Click to expand full call details (notes, timestamps, disposition)
    - Real-time updates via WebSocket
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 14.3 Write property tests for call board (Properties 10, 21)
    - **Property 10: Call board sorting by priority**
    - **Property 21: Priority color-code mapping**
    - **Validates: Requirements 5.5, 10.3**

  - [x] 14.4 Implement PersonSearch and VehicleSearch components
    - Person search form: query by name or DOB, display full person record
    - Vehicle search form: query by plate, make, or model, display full vehicle record
    - Results displayed within 2 seconds
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 14.5 Implement CitationForm and WarrantForm components
    - Citation form: person name, violation type, location, date, officer callsign
    - Warrant form: person name, charge, issuing authority, date
    - Submit to backend REST API
    - _Requirements: 12.1, 12.2_

  - [x] 14.6 Implement WarrantList component with filtering and "mark served" action
    - Display active warrants list
    - Filter by person name and charge type
    - "Mark served" button calls `PUT /api/warrants/:id/serve`
    - _Requirements: 12.5, 12.6_

  - [x] 14.7 Implement call notes and disposition editing
    - Allow updating call notes and disposition codes through the call detail view
    - Submit updates via `PUT /api/calls/:id`
    - _Requirements: 10.5_

- [x] 15. Checkpoint — Ensure CAD system tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Integration wiring and end-to-end flows
  - [x] 16.1 Wire plugin game state flow: plugin → backend → database upsert → CAD update
    - Backend receives game state on `/ws/plugin`, upserts peds/vehicles in MongoDB
    - CAD database stays current with game state
    - _Requirements: 7.4, 11.6_

  - [x] 16.2 Wire 911 call flow: plugin → backend → call creation → radio announcement + CAD update
    - Backend receives 911 event, creates CAD call via CallManager, broadcasts to radio and CAD
    - _Requirements: 5.2, 5.3, 8.2, 8.3_

  - [x] 16.3 Wire voice command flow: radio → backend → OpenAI → function call → database → radio response
    - Audio from radio forwarded to OpenAI, function calls dispatched to backend services, results returned to OpenAI, audio response sent back to radio
    - _Requirements: 1.3, 2.1, 15.3, 15.4, 15.5_

  - [x] 16.4 Wire status and call assignment flow: voice command → backend → status update → CAD broadcast
    - Officer status updates and call assignments propagate to CAD in real time
    - _Requirements: 4.1, 4.2, 4.3, 5.6_

  - [ ]* 16.5 Write integration tests for end-to-end data flows
    - Test 911 call → CAD call creation → radio announcement pipeline
    - Test voice plate/name check → database lookup → response pipeline
    - Test status update → CAD broadcast pipeline
    - _Requirements: 5.3, 8.3, 13.3_

- [x] 17. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (34 properties)
- The backend (Python/FastAPI) is the central hub — it is built first so other components can integrate against it
- The C# plugin uses FsCheck for property tests, the Python components use Hypothesis, and the React CAD uses fast-check
