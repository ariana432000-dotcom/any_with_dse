"use client";

import { useEffect, useRef, useState } from "react";
import { wsBaseUrl } from "@/lib/api";
import type { ExecutionEventPayload } from "@/lib/types";
import { ConnStatus, ReconnectingSocket } from "@/lib/ws";

interface UseAnalysisSocketResult {
  events: ExecutionEventPayload[];
  latest: ExecutionEventPayload | null;
  status: ConnStatus;
}

/** Live event stream for a single analysis run (backend: /ws/analysis/{id}). */
export function useAnalysisSocket(
  analysisId: string | null,
  active: boolean,
): UseAnalysisSocketResult {
  const [events, setEvents] = useState<ExecutionEventPayload[]>([]);
  const [status, setStatus] = useState<ConnStatus>("connecting");
  const socketRef = useRef<ReconnectingSocket<ExecutionEventPayload> | null>(null);

  useEffect(() => {
    if (!analysisId || !active) return;
    setEvents([]);

    const socket = new ReconnectingSocket<ExecutionEventPayload>(
      `${wsBaseUrl()}/ws/analysis/${encodeURIComponent(analysisId)}`,
    );
    socketRef.current = socket;

    const unsubMsg = socket.onMessage((evt) => {
      setEvents((prev) => [...prev, evt]);
    });
    const unsubStatus = socket.onStatusChange(setStatus);

    socket.connect();

    return () => {
      unsubMsg();
      unsubStatus();
      socket.close();
      socketRef.current = null;
    };
  }, [analysisId, active]);

  return { events, latest: events[events.length - 1] ?? null, status };
}
