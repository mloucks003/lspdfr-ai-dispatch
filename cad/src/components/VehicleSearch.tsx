/**
 * VehicleSearch — Search vehicles by plate, make, or model.
 * Display full vehicle record (Req 11.2, 11.3, 11.5).
 */

import React, { useState } from "react";
import type { Vehicle } from "../types";
import { searchVehicles } from "../utils/api";

export function VehicleSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await searchVehicles(query.trim());
      setResults(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="vehicle-search">
      <h2>Vehicle Search</h2>
      <form onSubmit={handleSearch} style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Plate, make, or model"
          style={{ flex: 1 }}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}

      {results.map((vehicle) => (
        <div key={vehicle._id} style={{ border: "1px solid #ccc", padding: "12px", marginBottom: "8px" }}>
          <h3>{vehicle.plate}</h3>
          <p><strong>Make:</strong> {vehicle.make}</p>
          <p><strong>Model:</strong> {vehicle.model}</p>
          <p><strong>Color:</strong> {vehicle.color}</p>
          <p><strong>Registered Owner:</strong> {vehicle.registered_owner}</p>
          {vehicle.flags.length > 0 && (
            <p><strong>Flags:</strong> {vehicle.flags.join(", ")}</p>
          )}
        </div>
      ))}

      {!loading && results.length === 0 && query && <p>No results found.</p>}
    </div>
  );
}
