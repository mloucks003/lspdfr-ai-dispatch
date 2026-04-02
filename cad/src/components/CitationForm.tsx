/**
 * CitationForm — Create citations with person name, violation type,
 * location, date, and officer callsign (Req 12.1).
 */

import React, { useState } from "react";
import { createCitation } from "../utils/api";

export function CitationForm() {
  const [personName, setPersonName] = useState("");
  const [violationType, setViolationType] = useState("");
  const [location, setLocation] = useState("");
  const [date, setDate] = useState("");
  const [officerCallsign, setOfficerCallsign] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await createCitation({
        person_name: personName,
        violation_type: violationType,
        location,
        date: date || new Date().toISOString(),
        officer_callsign: officerCallsign,
      });
      setSuccess(true);
      setPersonName("");
      setViolationType("");
      setLocation("");
      setDate("");
      setOfficerCallsign("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create citation");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="citation-form">
      <h2>Create Citation</h2>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "8px", maxWidth: "400px" }}>
        <input value={personName} onChange={(e) => setPersonName(e.target.value)} placeholder="Person Name" required />
        <input value={violationType} onChange={(e) => setViolationType(e.target.value)} placeholder="Violation Type" required />
        <input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location" required />
        <input type="datetime-local" value={date} onChange={(e) => setDate(e.target.value)} />
        <input value={officerCallsign} onChange={(e) => setOfficerCallsign(e.target.value)} placeholder="Officer Callsign" required />
        <button type="submit" disabled={submitting}>{submitting ? "Submitting…" : "Create Citation"}</button>
      </form>
      {success && <p style={{ color: "green" }}>Citation created.</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
