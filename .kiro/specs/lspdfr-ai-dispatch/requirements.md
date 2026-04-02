# Requirements Document

## Introduction

This document defines the requirements for an AI-powered police dispatch system designed to run alongside LSPDFR (a GTA V police mod). The system consists of four integrated components: an AI Dispatch Radio desktop companion app (Python) with continuous voice interaction via OpenAI Realtime API, an LSPDFR C# plugin that reads live game state, a web-based Computer Aided Dispatch (CAD) system (React + FastAPI), and a FastAPI backend that ties everything together with MongoDB persistence and WebSocket communication. The goal is to deliver an immersive, realistic police radio and dispatch experience using real 10-codes, GTA V locations, and game-aware data.

## Glossary

- **Dispatch_Radio**: The Python desktop companion application that provides continuous voice-based interaction between the player (officer) and an AI dispatcher using the OpenAI Realtime API.
- **LSPDFR_Plugin**: The C# RagePluginHook/LSPDFR plugin that reads live game state from GTA V and transmits it to the Backend.
- **CAD_System**: The web-based Computer Aided Dispatch interface (React frontend) used for managing active calls, unit status, and database lookups.
- **Backend**: The FastAPI server that orchestrates communication between all components, manages data persistence in MongoDB, and integrates with the OpenAI Realtime API.
- **Officer**: The player character controlled by the user within GTA V running LSPDFR.
- **Wake_Word**: The keyword "dispatch" that activates the Dispatch_Radio for voice command processing.
- **Ten_Code**: Standardized police radio brevity codes (e.g., 10-76 en route, 10-97 on scene, 10-98 clear) used for communication.
- **Game_State**: Live data from GTA V including nearby ped names, vehicle plates/models, player location, and wanted level.
- **CAD_Call**: A dispatch call record containing type, location, priority, assigned units, notes, and disposition.
- **BOLO**: Be On the Lookout — an alert broadcast to all units describing a suspect or vehicle of interest.
- **Ped**: A pedestrian NPC (non-player character) in GTA V.
- **Squelch_Effect**: Radio static/click audio effects applied to dispatcher voice output to simulate real police radio transmissions.
- **Function_Calling**: OpenAI API capability that allows the AI model to invoke defined functions (e.g., database lookups) during a conversation.
- **MongoDB**: The NoSQL document database used for persisting all system data including calls, persons, vehicles, citations, and warrants.

## Requirements

### Requirement 1: Wake Word Activation and Continuous Listening

**User Story:** As an officer, I want the dispatch radio to listen continuously and activate when I say "dispatch," so that I can communicate hands-free while playing.

#### Acceptance Criteria

1. WHILE the Dispatch_Radio is running, THE Dispatch_Radio SHALL continuously capture audio from the default microphone input.
2. WHEN the Officer speaks the Wake_Word "dispatch," THE Dispatch_Radio SHALL transition from passive listening to active command processing within 500ms.
3. WHILE the Dispatch_Radio is in active command processing mode, THE Dispatch_Radio SHALL stream the Officer's speech to the OpenAI Realtime API.
4. WHEN the Officer stops speaking for a configurable silence duration (default 2 seconds), THE Dispatch_Radio SHALL end the active command processing session and return to passive listening.
5. IF the default microphone is unavailable, THEN THE Dispatch_Radio SHALL display an error message identifying the missing audio device and retry connection every 5 seconds.

### Requirement 2: AI Dispatcher Voice Response

**User Story:** As an officer, I want the AI dispatcher to respond with realistic police radio voice, so that the experience feels immersive.

#### Acceptance Criteria

1. WHEN the OpenAI Realtime API returns a response, THE Dispatch_Radio SHALL play the audio response through the configured output device.
2. THE Dispatch_Radio SHALL apply Squelch_Effect audio processing (radio click-on, static, click-off) to all dispatcher voice output.
3. THE Backend SHALL provide the OpenAI Realtime API with a system prompt instructing the AI to use Ten_Code protocol, police radio brevity, and a professional dispatcher tone.
4. WHEN the AI dispatcher responds, THE Dispatch_Radio SHALL prefix each transmission with the Officer's unit callsign.
5. IF the OpenAI Realtime API connection fails, THEN THE Dispatch_Radio SHALL notify the Officer with an audible error tone and attempt reconnection every 10 seconds.

### Requirement 3: Name and Plate Checks

**User Story:** As an officer, I want to request name and plate checks through voice, so that I can look up suspect and vehicle information without leaving the game.

#### Acceptance Criteria

1. WHEN the Officer requests a plate check via voice, THE Backend SHALL query the vehicle database in MongoDB and return the vehicle make, model, color, registered owner, and any associated flags.
2. WHEN the Officer requests a name check via voice, THE Backend SHALL query the person database in MongoDB and return the person's name, date of birth, physical description, and any active warrants or priors.
3. THE Backend SHALL expose plate check and name check as Function_Calling definitions to the OpenAI Realtime API so the AI dispatcher can invoke them during conversation.
4. WHEN a queried plate or name has no matching record, THE Dispatch_Radio SHALL respond with "no record on file" using standard radio protocol.
5. IF the MongoDB connection is unavailable during a lookup, THEN THE Backend SHALL return an error and THE Dispatch_Radio SHALL inform the Officer that the system is temporarily unavailable.

### Requirement 4: Officer Status Tracking

**User Story:** As an officer, I want to update and track my status using 10-codes, so that dispatch and the CAD system reflect my current activity.

#### Acceptance Criteria

1. WHEN the Officer communicates a status Ten_Code (10-76 en route, 10-97 on scene, 10-98 clear, 10-8 in service, 10-7 out of service), THE Backend SHALL update the Officer's status record in MongoDB.
2. THE CAD_System SHALL display the current status of all tracked units in real time.
3. WHEN the Officer's status changes, THE Backend SHALL broadcast the updated status to the CAD_System via WebSocket within 1 second.
4. THE Backend SHALL expose officer status update as a Function_Calling definition so the AI dispatcher can update status based on voice commands.
5. WHEN the Officer provides a status update, THE Dispatch_Radio SHALL acknowledge the status change using proper radio protocol (e.g., "Copy, unit [callsign], 10-76").

### Requirement 5: Dispatch Call Generation

**User Story:** As an officer, I want to receive realistic dispatch calls with actual GTA V locations and details, so that gameplay feels authentic.

#### Acceptance Criteria

1. THE Backend SHALL generate CAD_Calls with realistic details including call type (robbery, traffic stop, domestic disturbance, etc.), specific GTA V street addresses and landmarks, suspect descriptions, and priority level.
2. WHEN the LSPDFR_Plugin detects a game event (e.g., crime in progress, NPC calling 911), THE LSPDFR_Plugin SHALL send the event data to the Backend via WebSocket.
3. WHEN a new CAD_Call is created, THE Backend SHALL broadcast the call to the Dispatch_Radio and the CAD_System simultaneously.
4. WHEN the Dispatch_Radio receives a new call, THE Dispatch_Radio SHALL announce the call using voice with Squelch_Effect and proper radio protocol.
5. THE CAD_System SHALL display all active CAD_Calls on a call board sorted by priority level (highest priority first).
6. WHEN the Officer accepts a call via voice, THE Backend SHALL assign the Officer to that CAD_Call and update the Officer's status to 10-76 (en route).

### Requirement 6: Backup, BOLO, and Warrant Requests

**User Story:** As an officer, I want to request backup, issue BOLOs, and check warrants through voice, so that I have full dispatch support during gameplay.

#### Acceptance Criteria

1. WHEN the Officer requests backup via voice, THE Backend SHALL create a high-priority CAD_Call at the Officer's current location and broadcast it to all connected units.
2. WHEN the Officer issues a BOLO via voice, THE Backend SHALL create a BOLO record in MongoDB containing the suspect or vehicle description and broadcast the BOLO to the CAD_System.
3. WHEN the Officer requests a warrant check via voice, THE Backend SHALL query the person database for active warrants and return the results through the AI dispatcher.
4. THE Backend SHALL expose backup request, BOLO creation, and warrant check as Function_Calling definitions to the OpenAI Realtime API.
5. WHEN a backup request is made, THE Dispatch_Radio SHALL announce the request with the Officer's location and a "units respond" directive using radio protocol.

### Requirement 7: LSPDFR Plugin Game State Reading

**User Story:** As a developer, I want the LSPDFR plugin to read live game state, so that the AI dispatch system has access to current in-game data.

#### Acceptance Criteria

1. THE LSPDFR_Plugin SHALL read nearby Ped names, vehicle plates, vehicle models, and vehicle colors from the GTA V game world.
2. THE LSPDFR_Plugin SHALL read the Officer's current map coordinates and translate them to the nearest GTA V street name or landmark.
3. THE LSPDFR_Plugin SHALL read the current wanted level of the Officer's target Ped.
4. WHEN Game_State changes (new Peds nearby, vehicle detected, location change exceeding 50 meters), THE LSPDFR_Plugin SHALL send updated Game_State to the Backend via WebSocket.
5. IF the WebSocket connection to the Backend is lost, THEN THE LSPDFR_Plugin SHALL buffer Game_State updates locally and transmit them when the connection is restored.
6. THE LSPDFR_Plugin SHALL send Game_State updates at a maximum rate of once per second to avoid performance degradation in GTA V.

### Requirement 8: LSPDFR Plugin 911 Call Generation

**User Story:** As an officer, I want the plugin to generate realistic 911 calls based on game events, so that dispatch calls feel organic and tied to gameplay.

#### Acceptance Criteria

1. WHEN a crime event occurs in the GTA V game world near the Officer, THE LSPDFR_Plugin SHALL generate a 911 call event containing the crime type, location, and involved Ped descriptions.
2. THE LSPDFR_Plugin SHALL send generated 911 call events to the Backend via WebSocket.
3. WHEN the Backend receives a 911 call event, THE Backend SHALL create a corresponding CAD_Call with appropriate priority level and details.
4. THE LSPDFR_Plugin SHALL include caller description (e.g., "female caller reports...") to add realism to generated 911 calls.

### Requirement 9: Ped Criminal History

**User Story:** As an officer, I want peds to have criminal history records, so that name checks return realistic background information.

#### Acceptance Criteria

1. THE Backend SHALL maintain a person database in MongoDB containing records with fields for name, date of birth, physical description, prior offenses, active warrants, and license status.
2. WHEN the LSPDFR_Plugin encounters a new Ped, THE LSPDFR_Plugin SHALL send the Ped's name and physical description to the Backend.
3. WHEN the Backend receives a new Ped that has no existing record, THE Backend SHALL generate a criminal history profile with randomized but realistic priors, warrant status, and license status.
4. WHEN the Officer requests a name check, THE Backend SHALL return the full criminal history record for the queried Ped.
5. THE Backend SHALL persist all generated criminal history records in MongoDB so that the same Ped returns consistent results across sessions.

### Requirement 10: CAD System Active Calls Board

**User Story:** As an officer, I want a visual call board showing all active dispatch calls, so that I can see the full picture of ongoing incidents.

#### Acceptance Criteria

1. THE CAD_System SHALL display a list of all active CAD_Calls with columns for call number, type, priority, location, assigned units, and status.
2. WHEN a new CAD_Call is created or an existing call is updated, THE CAD_System SHALL reflect the change within 1 second via WebSocket.
3. THE CAD_System SHALL color-code calls by priority level (red for high, yellow for medium, green for low).
4. WHEN the Officer clicks on a CAD_Call, THE CAD_System SHALL display the full call details including notes, timestamps, and disposition.
5. THE CAD_System SHALL allow the Officer to update call notes and disposition codes through the web interface.

### Requirement 11: CAD System Person and Vehicle Database

**User Story:** As an officer, I want to search the person and vehicle database through the CAD interface, so that I can look up records visually.

#### Acceptance Criteria

1. THE CAD_System SHALL provide a search interface for querying the person database by name or date of birth.
2. THE CAD_System SHALL provide a search interface for querying the vehicle database by plate number, make, or model.
3. WHEN a search is submitted, THE CAD_System SHALL display matching results within 2 seconds.
4. THE CAD_System SHALL display person records with name, date of birth, physical description, prior offenses, active warrants, and license status.
5. THE CAD_System SHALL display vehicle records with plate number, make, model, color, registered owner, and any flags.
6. WHEN the LSPDFR_Plugin sends new Ped or vehicle data, THE Backend SHALL upsert the records in MongoDB so the CAD_System database stays current with game state.

### Requirement 12: Citation and Warrant Management

**User Story:** As an officer, I want to create citations and manage warrants through the CAD system, so that I can track enforcement actions.

#### Acceptance Criteria

1. THE CAD_System SHALL provide a form for creating citations with fields for person name, violation type, location, date, and officer callsign.
2. THE CAD_System SHALL provide a form for creating warrants with fields for person name, charge, issuing authority, and date.
3. WHEN a citation is created, THE Backend SHALL store the citation in MongoDB and associate it with the person's record.
4. WHEN a warrant is created, THE Backend SHALL store the warrant in MongoDB and flag the person's record as having an active warrant.
5. THE CAD_System SHALL display a list of all active warrants with filtering by person name and charge type.
6. WHEN a warrant is served, THE CAD_System SHALL allow the Officer to mark the warrant as served, and THE Backend SHALL update the warrant status in MongoDB.

### Requirement 13: Backend WebSocket Communication

**User Story:** As a developer, I want the backend to manage WebSocket connections to all components, so that data flows in real time across the system.

#### Acceptance Criteria

1. THE Backend SHALL maintain concurrent WebSocket connections to the Dispatch_Radio, the LSPDFR_Plugin, and the CAD_System.
2. THE Backend SHALL maintain a WebSocket connection to the OpenAI Realtime API for voice-to-voice AI interaction.
3. WHEN the Backend receives data from the LSPDFR_Plugin, THE Backend SHALL process the data and broadcast relevant updates to the Dispatch_Radio and CAD_System within 500ms.
4. IF a WebSocket client disconnects, THEN THE Backend SHALL log the disconnection and accept reconnection without data loss for pending updates.
5. THE Backend SHALL authenticate WebSocket connections using a shared API key before accepting data.

### Requirement 14: Backend Data Persistence

**User Story:** As a developer, I want all system data persisted in MongoDB, so that records survive across sessions.

#### Acceptance Criteria

1. THE Backend SHALL store all CAD_Calls, person records, vehicle records, citations, warrants, and BOLO records in MongoDB.
2. THE Backend SHALL expose RESTful API endpoints for CRUD operations on all data collections (calls, persons, vehicles, citations, warrants, BOLOs).
3. WHEN the Backend starts, THE Backend SHALL verify the MongoDB connection and create required collections and indexes if they do not exist.
4. IF the MongoDB connection fails during operation, THEN THE Backend SHALL queue write operations in memory and retry the connection every 5 seconds.
5. THE Backend SHALL log all database write operations with timestamps for audit purposes.

### Requirement 15: OpenAI Realtime API Integration

**User Story:** As a developer, I want the backend to integrate with the OpenAI Realtime API for voice-to-voice interaction, so that the AI dispatcher can converse naturally with the officer.

#### Acceptance Criteria

1. THE Backend SHALL establish a WebSocket connection to the OpenAI Realtime API using the configured API key.
2. THE Backend SHALL register Function_Calling definitions for plate check, name check, warrant check, officer status update, backup request, BOLO creation, and call assignment.
3. WHEN the Dispatch_Radio streams audio to the Backend, THE Backend SHALL forward the audio to the OpenAI Realtime API in the required format.
4. WHEN the OpenAI Realtime API returns audio, THE Backend SHALL forward the audio to the Dispatch_Radio for playback.
5. WHEN the OpenAI Realtime API invokes a Function_Calling definition, THE Backend SHALL execute the corresponding database operation and return the result to the API.
6. THE Backend SHALL include a system prompt instructing the AI to behave as a professional police dispatcher using Ten_Code protocol, radio brevity, and GTA V location awareness.
7. IF the OpenAI Realtime API WebSocket connection drops, THEN THE Backend SHALL attempt reconnection with exponential backoff starting at 1 second up to a maximum of 60 seconds.
