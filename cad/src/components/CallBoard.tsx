/**
 * CallBoard — Active calls table sorted by priority.
 * Color-coded by priority: red (1), yellow (2), green (3).
 * Click to expand full call details.
 * Real-time updates via WebSocket (Req 10.1, 10.2, 10.3, 10.4).
 */

import React, { useEffect, useState } from "react";
import type { CADCall } from "../types";
import { getCalls } from "../utils/api";
import { getPriorityColor } from "../utils/colors";
import { useWebSocket } from "../context/WebSocketProvider";
import { CallDetail } from "./CallDetail";

export function CallBoard() {
  const [calls, setCalls] = useState<CADCall[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { lastCallUpdate } = useWebSocket();

  // Initial fetch
  useEffect(() => {
    getCalls()
      .then((data) => {
        setCalls(sortByPriority(data));
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load calls");
        setLoading(false);
      });
  }, []);

  // Real-time updates via WebSocket
  useEffect(() => {
    if (!lastCallUpdate) return;
    setCalls((prev) => {
      const idx = prev.findIndex((c) => c._id === lastCallUpdate._id);
      let updated: CADCall[];
      if (idx >= 0) {
        updated = [...prev];
        updated[idx] = lastCallUpdate;
      } else {
        updated = [...prev, lastCallUpdate];
      }
      return sortByPriority(updated);
    });
  }, [lastCallUpdate]);

  const handleCallUpdated = (updated: CADCall) => {
    setCalls((prev) => {
      const idx = prev.findIndex((c) => c._id === updated._id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = updated;
        return sortByPriority(next);
      }
      return prev;
    });
  };

  if (loading) return <p>Loading calls…</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  return (
    <div className="call-board">
      <h2>Active Calls</h2>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th>Call #</th>
            <th>Type</th>
            <th>Priority</th>
            <th>Location</th>
            <th>Assigned Units</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((call) => (
            <React.Fragment key={call._id}>
              <tr
                onClick={() => setExpandedId(expandedId === call._id ? null : call._id)}
                style={{
                  backgroundColor: getPriorityColor(call.priority),
                  cursor: "pointer",
                  color: call.priority === 2 ? "#000" : "#fff",
                }}
              >
                <td>{call.call_number}</td>
                <td>{call.type}</td>
                <td>{call.priority}</td>
                <td>{call.location.street}</td>
                <td>{call.assigned_units.join(", ") || "—"}</td>
                <td>{call.status}</td>
              </tr>
              {expandedId === call._id && (
                <tr>
                  <td colSpan={6}>
                    <CallDetail call={call} onUpdated={handleCallUpdated} />
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
      {calls.length === 0 && <p>No active calls.</p>}
    </div>
  );
}

/** Sort calls by priority ascending (1 first). */
function sortByPriority(calls: CADCall[]): CADCall[] {
  return [...calls].sort((a, b) => a.priority - b.priority);
}
