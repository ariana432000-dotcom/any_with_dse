"use client";

import { useEffect, useRef, useState } from "react";
import { wsBaseUrl } from "@/lib/api";
import type { ExecutionEventPayload } from "@/lib/types";
import { ConnStatus, ReconnectingSocket } from "@/lib/ws";

/** Global live activity feed (backend: /ws) — every running analysis's events. */
export function useLiveFeed(maxItems = 30) {
  const [events, setEvents] = useState<ExecutionEventPayload[]>([]);
  const [status, setStatus] = useState<ConnStatus>("connecting");
  const socketRef = useRef<ReconnectingSocket<ExecutionEventPayload> | null>(null);

  useEffect(() => {
    const socket = new ReconnectingSocket<ExecutionEventPayload>(`${wsBaseUrl()}/ws`);
    socketRef.current = socket;

    const unsubMsg = socket.onMessage((evt) => {
      if (evt.type === "connected" || evt.type === "pong") return;
      setEvents((prev) => [evt, ...prev].slice(0, maxItems));
    });
    const unsubStatus = socket.onStatusChange(setStatus);

    socket.connect();
    const pingInterval = setInterval(() => socket.send("ping"), 25_000);

    return () => {
      unsubMsg();
      unsubStatus();
      clearInterval(pingInterval);
      socket.close();
      socketRef.current = null;
    };
  }, [maxItems]);

  return { events, status };
}
