/**
 * WarrantList — Display active warrants with filtering and "mark served" action.
 * Filter by person name and charge type (Req 12.5, 12.6).
 */

import React, { useEffect, useState } from "react";
import type { Warrant } from "../types";
import { getWarrants, serveWarrant } from "../utils/api";

export function WarrantList() {
  const [warrants, setWarrants] = useState<Warrant[]>([]);
  const [nameFilter, setNameFilter] = useState("");
  const [chargeFilter, setChargeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchWarrants = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getWarrants({
        active: true,
        person_name: nameFilter || undefined,
        charge: chargeFilter || undefined,
      });
      setWarrants(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load warrants");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWarrants();
  }, []);

  const handleFilter = (e: React.FormEvent) => {
    e.preventDefault();
    fetchWarrants();
  };

  const handleServe = async (id: string) => {
    try {
      const updated = await serveWarrant(id);
      // Remove served warrant from the active list
      setWarrants((prev) => prev.filter((w) => w._id !== updated._id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to serve warrant");
    }
  };

  return (
    <div className="warrant-list">
      <h2>Active Warrants</h2>

      <form onSubmit={handleFilter} style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
        <input
          type="text"
          value={nameFilter}
          onChange={(e) => setNameFilter(e.target.value)}
          placeholder="Filter by person name"
        />
        <input
          type="text"
          value={chargeFilter}
          onChange={(e) => setChargeFilter(e.target.value)}
          placeholder="Filter by charge"
        />
        <button type="submit">Filter</button>
      </form>

      {error && <p style={{ color: "red" }}>{error}</p>}
      {loading && <p>Loading warrants…</p>}

      {!loading && warrants.length === 0 && <p>No active warrants found.</p>}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th>Person</th>
            <th>Charge</th>
            <th>Issuing Authority</th>
            <th>Date Issued</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {warrants.map((w) => (
            <tr key={w._id}>
              <td>{w.person_name}</td>
              <td>{w.charge}</td>
              <td>{w.issuing_authority}</td>
              <td>{new Date(w.date_issued).toLocaleDateString()}</td>
              <td>
                <button onClick={() => handleServe(w._id)}>Mark Served</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
