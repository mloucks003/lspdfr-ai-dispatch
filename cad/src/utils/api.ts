/**
 * REST API helper functions for all backend endpoints.
 */

import type { CADCall, Person, Vehicle, Citation, Warrant } from "../types";

const BASE_URL = "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

// --- Calls ---

export function getCalls(): Promise<CADCall[]> {
  return request<CADCall[]>("/api/calls");
}

export function getCall(id: string): Promise<CADCall> {
  return request<CADCall>(`/api/calls/${id}`);
}

export function updateCall(
  id: string,
  body: { note?: { text: string; author: string }; disposition?: string }
): Promise<CADCall> {
  return request<CADCall>(`/api/calls/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// --- Persons ---

export function searchPersons(query: string): Promise<Person[]> {
  return request<Person[]>(`/api/persons?q=${encodeURIComponent(query)}`);
}

// --- Vehicles ---

export function searchVehicles(query: string): Promise<Vehicle[]> {
  return request<Vehicle[]>(`/api/vehicles?q=${encodeURIComponent(query)}`);
}

// --- Citations ---

export function createCitation(data: {
  person_name: string;
  violation_type: string;
  location: string;
  date: string;
  officer_callsign: string;
}): Promise<Citation> {
  return request<Citation>("/api/citations", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// --- Warrants ---

export function getWarrants(params?: {
  active?: boolean;
  person_name?: string;
  charge?: string;
}): Promise<Warrant[]> {
  const searchParams = new URLSearchParams();
  if (params?.active !== undefined) searchParams.set("active", String(params.active));
  if (params?.person_name) searchParams.set("person_name", params.person_name);
  if (params?.charge) searchParams.set("charge", params.charge);
  const qs = searchParams.toString();
  return request<Warrant[]>(`/api/warrants${qs ? `?${qs}` : ""}`);
}

export function createWarrant(data: {
  person_name: string;
  charge: string;
  issuing_authority: string;
  date_issued: string;
}): Promise<Warrant> {
  return request<Warrant>("/api/warrants", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function serveWarrant(id: string): Promise<Warrant> {
  return request<Warrant>(`/api/warrants/${id}/serve`, { method: "PUT" });
}
