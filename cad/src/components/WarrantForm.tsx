/**
 * WarrantForm — Create warrants with person name, charge,
 * issuing authority, and date (Req 12.2).
 */

import React, { useState } from "react";
import { createWarrant } from "../utils/api";

export function WarrantForm() {
  const [personName, setPersonName] = useState("");
  const [charge, setCharge] = useState("");
  const [issuingAuthority, setIssuingAuthority] = useState("");
  const [dateIssued, setDateIssued] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);
    try {
      await createWarrant({
        person_name: personName,
        charge,
        issuing_authority: issuingAuthority,
        date_issued: dateIssued || new Date().toISOString(),
      });
      setSuccess(true);
      setPersonName("");
      setCharge("");
      setIssuingAuthority("");
      setDateIssued("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create warrant");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="warrant-form">
      <h2>Create Warrant</h2>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "8px", maxWidth: "400px" }}>
        <input value={personName} onChange={(e) => setPersonName(e.target.value)} placeholder="Person Name" required />
        <input value={charge} onChange={(e) => setCharge(e.target.value)} placeholder="Charge" required />
        <input value={issuingAuthority} onChange={(e) => setIssuingAuthority(e.target.value)} placeholder="Issuing Authority" required />
        <input type="datetime-local" value={dateIssued} onChange={(e) => setDateIssued(e.target.value)} />
        <button type="submit" disabled={submitting}>{submitting ? "Submitting…" : "Create Warrant"}</button>
      </form>
      {success && <p style={{ color: "green" }}>Warrant created.</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
