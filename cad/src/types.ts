/**
 * TypeScript interfaces matching backend Pydantic data models.
 */

// --- Enums ---

export type CallStatus = "pending" | "dispatched" | "on_scene" | "closed";
export type WarrantStatus = "active" | "served";
export type BOLOStatus = "active" | "cancelled";
export type LicenseStatus = "valid" | "suspended" | "revoked" | "none";

// --- Nested / shared types ---

export interface Coordinates {
  x: number;
  y: number;
  z: number;
}

export interface Location {
  street: string;
  landmark?: string | null;
  coordinates?: Coordinates | null;
}

export interface CallNote {
  text: string;
  timestamp: string;
  author: string;
}

export interface PhysicalDescription {
  gender: string;
  race: string;
  height: string;
  weight: string;
  hair_color: string;
  distinguishing_marks?: string | null;
}

export interface PriorOffense {
  offense: string;
  date: string;
  disposition: string;
}

// --- Top-level collection models ---

export interface CADCall {
  _id: string;
  call_number: string | null;
  type: string;
  priority: number;
  location: Location;
  description: string;
  suspect_description?: string | null;
  assigned_units: string[];
  status: CallStatus;
  notes: CallNote[];
  disposition?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Person {
  _id: string;
  name: string;
  date_of_birth: string;
  physical_description: PhysicalDescription;
  prior_offenses: PriorOffense[];
  active_warrants: string[];
  license_status: LicenseStatus;
  created_at: string;
  updated_at: string;
}

export interface Vehicle {
  _id: string;
  plate: string;
  make: string;
  model: string;
  color: string;
  registered_owner: string;
  flags: string[];
  created_at: string;
  updated_at: string;
}

export interface Citation {
  _id: string;
  person_name: string;
  person_id?: string | null;
  violation_type: string;
  location: string;
  date: string;
  officer_callsign: string;
  created_at: string;
}

export interface Warrant {
  _id: string;
  person_name: string;
  person_id?: string | null;
  charge: string;
  issuing_authority: string;
  date_issued: string;
  status: WarrantStatus;
  date_served?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BOLO {
  _id: string;
  description: string;
  suspect_description?: string | null;
  vehicle_description?: string | null;
  issuing_officer: string;
  status: BOLOStatus;
  created_at: string;
  updated_at: string;
}

// --- WebSocket message types (Backend → CAD) ---

export interface CallUpdateMessage {
  type: "call_update";
  call: CADCall;
}

export interface StatusUpdateMessage {
  type: "status_update";
  unit: string;
  status: string;
}

export interface BOLOAlertMessage {
  type: "bolo_alert";
  bolo: BOLO;
}

export type WSMessage = CallUpdateMessage | StatusUpdateMessage | BOLOAlertMessage;
