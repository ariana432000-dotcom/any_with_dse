/**
 * A tiny auto-reconnecting WebSocket wrapper. Used by hooks/useLiveFeed.ts and
 * hooks/useAnalysisSocket.ts to talk to the backend's `/ws` and
 * `/ws/analysis/{id}` endpoints (see backend/app/api/ws.py and
 * backend/app/api/routes/analysis.py).
 */
export type WsListener<T> = (data: T) => void;

export class ReconnectingSocket<T = unknown> {
  private url: string;
  private ws: WebSocket | null = null;
  private listeners = new Set<WsListener<T>>();
  private statusListeners = new Set<(status: ConnStatus) => void>();
  private closedByUser = false;
  private retryMs = 1000;
  private readonly maxRetryMs = 15_000;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private status: ConnStatus = "connecting";

  constructor(url: string) {
    this.url = url;
  }

  connect(): void {
    if (typeof window === "undefined") return;
    this.closedByUser = false;
    this.open();
  }

  private open(): void {
    this.setStatus("connecting");
    try {
      this.ws = new WebSocket(this.url);
    } catch {
      this.scheduleRetry();
      return;
    }

    this.ws.onopen = () => {
      this.retryMs = 1000;
      this.setStatus("open");
    };

    this.ws.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data) as T;
        this.listeners.forEach((l) => l(parsed));
      } catch {
        // ignore malformed frames
      }
    };

    this.ws.onclose = () => {
      this.setStatus("closed");
      if (!this.closedByUser) this.scheduleRetry();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  private scheduleRetry(): void {
    if (this.retryTimer) return;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      if (!this.closedByUser) this.open();
    }, this.retryMs);
    this.retryMs = Math.min(this.retryMs * 1.6, this.maxRetryMs);
  }

  private setStatus(status: ConnStatus): void {
    this.status = status;
    this.statusListeners.forEach((l) => l(status));
  }

  getStatus(): ConnStatus {
    return this.status;
  }

  onMessage(listener: WsListener<T>): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onStatusChange(listener: (status: ConnStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  send(data: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(data);
  }

  close(): void {
    this.closedByUser = true;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.ws?.close();
  }
}

export type ConnStatus = "connecting" | "open" | "closed";
