/**
 * Main CAD application — tabs for CallBoard, searches, forms, and warrants.
 */

import React, { useState } from "react";
import { WebSocketProvider } from "./context/WebSocketProvider";
import { CallBoard } from "./components/CallBoard";
import { PersonSearch } from "./components/PersonSearch";
import { VehicleSearch } from "./components/VehicleSearch";
import { CitationForm } from "./components/CitationForm";
import { WarrantForm } from "./components/WarrantForm";
import { WarrantList } from "./components/WarrantList";

type Tab = "calls" | "persons" | "vehicles" | "citations" | "warrants" | "warrant-list";

const TABS: { key: Tab; label: string }[] = [
  { key: "calls", label: "Call Board" },
  { key: "persons", label: "Person Search" },
  { key: "vehicles", label: "Vehicle Search" },
  { key: "citations", label: "New Citation" },
  { key: "warrants", label: "New Warrant" },
  { key: "warrant-list", label: "Active Warrants" },
];

const API_KEY = "dev-api-key";

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("calls");

  return (
    <WebSocketProvider apiKey={API_KEY}>
      <div style={{ fontFamily: "sans-serif", padding: "16px" }}>
        <h1>LSPDFR CAD System</h1>
        <nav style={{ display: "flex", gap: "4px", marginBottom: "16px" }}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: "8px 16px",
                fontWeight: activeTab === tab.key ? "bold" : "normal",
                borderBottom: activeTab === tab.key ? "2px solid #333" : "none",
              }}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        {activeTab === "calls" && <CallBoard />}
        {activeTab === "persons" && <PersonSearch />}
        {activeTab === "vehicles" && <VehicleSearch />}
        {activeTab === "citations" && <CitationForm />}
        {activeTab === "warrants" && <WarrantForm />}
        {activeTab === "warrant-list" && <WarrantList />}
      </div>
    </WebSocketProvider>
  );
}
