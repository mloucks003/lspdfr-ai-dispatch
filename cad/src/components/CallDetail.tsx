/**
 * CallDetail — Expanded view for a single CAD call.
 * Shows full details: notes, timestamps, disposition.
 * Allows editing call notes and disposition (Req 10.5).
 */

import React, { useState } from "react";
import type { CADCall } from "../types";
import { updateCall } from "../utils/api";
import { getPriorityColor } from "../utils/colors";

interface CallDetailProps {
  call: CADCall;
  onUpdated: (updated: CADCall) => void;
}

export function CallDetail({ call, onUpdated }: CallDetailProps) {
  const [noteText, setNoteText] = useState("");
  const [noteAuthor, setNoteAuthor] = useState("");
  const [disposition, setDisposition] = useState(call.disposition ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAddNote = async () => {
    if (!noteText.trim() || !noteAuthor.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await updateCall(call._id, {
        note: { text: noteText.trim(), author: noteAuthor.trim() },
      });
      onUpdated(updated);
      setNoteText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add note");
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdateDisposition = async () => {
    if (!disposition.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await updateCall(call._id, {
        disposition: disposition.trim(),
      });
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update disposition");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="call-detail" style={{ padding: "12px", borderLeft: `4px solid ${getPriorityColor(call.priority)}` }}>
      <h3>Call #{call.call_number} — {call.type}</h3>
      <p><strong>Status:</strong> {call.status}</p>
      <p><strong>Priority:</strong> {call.priority}</p>
      <p><strong>Location:</strong> {call.location.street}{call.location.landmark ? ` (${call.location.landmark})` : ""}</p>
      <p><strong>Description:</strong> {call.description}</p>
      {call.suspect_description && <p><strong>Suspect:</strong> {call.suspect_description}</p>}
      <p><strong>Assigned Units:</strong> {call.assigned_units.length > 0 ? call.assigned_units.join(", ") : "None"}</p>
      <p><strong>Created:</strong> {new Date(call.created_at).toLocaleString()}</p>
      <p><strong>Updated:</strong> {new Date(call.updated_at).toLocaleString()}</p>

      {/* Disposition editing */}
      <div style={{ marginTop: "12px" }}>
        <label><strong>Disposition:</strong></label>
        <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
          <input
            type="text"
            value={disposition}
            onChange={(e) => setDisposition(e.target.value)}
            placeholder="Enter disposition code"
          />
          <button onClick={handleUpdateDisposition} disabled={submitting}>
            Update Disposition
          </button>
        </div>
      </div>

      {/* Notes section */}
      <div style={{ marginTop: "12px" }}>
        <strong>Notes:</strong>
        {call.notes.length === 0 && <p>No notes yet.</p>}
        <ul>
          {call.notes.map((note, i) => (
            <li key={i}>
              <em>{new Date(note.timestamp).toLocaleString()}</em> — <strong>{note.author}:</strong> {note.text}
            </li>
          ))}
        </ul>
      </div>

      {/* Add note form */}
      <div style={{ marginTop: "8px" }}>
        <label><strong>Add Note:</strong></label>
        <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
          <input
            type="text"
            value={noteAuthor}
            onChange={(e) => setNoteAuthor(e.target.value)}
            placeholder="Author"
            style={{ width: "120px" }}
          />
          <input
            type="text"
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            placeholder="Note text"
            style={{ flex: 1 }}
          />
          <button onClick={handleAddNote} disabled={submitting}>
            Add Note
          </button>
        </div>
      </div>

      {error && <p style={{ color: "red", marginTop: "8px" }}>{error}</p>}
    </div>
  );
}
