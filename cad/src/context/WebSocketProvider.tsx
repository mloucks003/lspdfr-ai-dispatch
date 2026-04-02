/**
 * WebSocket context provider for real-time CAD updates.
 * Connects to ws://localhost:8000/ws/cad and exposes incoming messages
 * (call_update, status_update, bolo_alert) via React context.
 */

import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import type { WSMessage, CADCall, BOLO } from "../types";

interface UnitStatus {
  unit: string;
  status: string;
}

interface WebSocketContextValue {
  /** Most recent call update received via WebSocket */
  lastCallUpdate: CADCall | null;
  /** Most recent unit status update */
  lastStatusUpdate: UnitStatus | null;
  /** Most recent BOLO alert */
  lastBOLOAlert: BOLO | null;
  /** Whether the WebSocket is currently connected */
  connected: boolean;
}

const WebSocketContext = createContext<WebSocketContextValue>({
  lastCallUpdate: null,
  lastStatusUpdate: null,
  lastBOLOAlert: null,
  connected: false,
});

export function useWebSocket(): WebSocketContextValue {
  return useContext(WebSocketContext);
}

interface WebSocketProviderProps {
  apiKey: string;
  children: ReactNode;
}

export function WebSocketProvider({ apiKey, children }: WebSocketProviderProps) {
  const [connected, setConnected] = useState(false);
  const [lastCallUpdate, setLastCallUpdate] = useState<CADCall | null>(null);
  const [lastStatusUpdate, setLastStatusUpdate] = useState<UnitStatus | null>(null);
  const [lastBOLOAlert, setLastBOLOAlert] = useState<BOLO | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    const url = `ws://localhost:8000/ws/cad?api_key=${encodeURIComponent(apiKey)}`;
    const ws = new WebSocket(url);

    ws.onopen = () => setConnected(true);

    ws.onclose = () => {
      setConnected(false);
      // Reconnect after 5 seconds
      reconnectTimer.current = setTimeout(connect, 5000);
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (event) => {
      try {
        const msg: WSMessage = JSON.parse(event.data);
        switch (msg.type) {
          case "call_update":
            setLastCallUpdate(msg.call);
            break;
          case "status_update":
            setLastStatusUpdate({ unit: msg.unit, status: msg.status });
            break;
          case "bolo_alert":
            setLastBOLOAlert(msg.bolo);
            break;
        }
      } catch {
        // Ignore malformed messages
      }
    };

    wsRef.current = ws;
  }, [apiKey]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const value: WebSocketContextValue = {
    lastCallUpdate,
    lastStatusUpdate,
    lastBOLOAlert,
    connected,
  };

  return (
    <WebSocketContext.Provider value={value}>{children}</WebSocketContext.Provider>
  );
}
