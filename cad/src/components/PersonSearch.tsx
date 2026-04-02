/**
 * PersonSearch — Search persons by name or DOB, display full record.
 * Results displayed within 2 seconds (Req 11.1, 11.3, 11.4).
 */

import React, { useState } from "react";
import type { Person } from "../types";
import { searchPersons } from "../utils/api";

export function PersonSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Person[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await searchPersons(query.trim());
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="person-search">
      <h2>Person Search</h2>
      <form onSubmit={handleSearch} style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Name or DOB (YYYY-MM-DD)"
          style={{ flex: 1 }}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {results.map((person) => (
        <div key={person._id} style={{ border: "1px solid #ccc", padding: "12px", marginBottom: "8px" }}>
          <h3>{person.name}</h3>
          <p><strong>DOB:</strong> {person.date_of_birth}</p>
          <p><strong>License:</strong> {person.license_status}</p>
          <p>
            <strong>Description:</strong>{" "}
            {person.physical_description.gender}, {person.physical_description.race},{" "}
            {person.physical_description.height}, {person.physical_description.weight},{" "}
            {person.physical_description.hair_color}
            {person.physical_description.distinguishing_marks
              ? ` — ${person.physical_description.distinguishing_marks}`
              : ""}
          </p>
          {person.prior_offenses.length > 0 && (
            <div>
              <strong>Prior Offenses:</strong>
              <ul>
                {person.prior_offenses.map((o, i) => (
                  <li key={i}>{o.offense} ({o.date}) — {o.disposition}</li>
                ))}
              </ul>
            </div>
          )}
          {person.active_warrants.length > 0 && (
            <p><strong>Active Warrants:</strong> {person.active_warrants.length}</p>
          )}
        </div>
      ))}

      {!loading && results.length === 0 && query && <p>No results found.</p>}
    </div>
  );
}
