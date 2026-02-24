import type { WSMessage } from "@/types/editor";

export interface WSCallbacks {
  onProgress?: (msg: Extract<WSMessage, { type: "progress" }>) => void;
  onCompleted?: (msg: Extract<WSMessage, { type: "completed" }>) => void;
  onError?: (msg: Extract<WSMessage, { type: "error" }>) => void;
  onLog?: (msg: Extract<WSMessage, { type: "log" }>) => void;
  onDisconnect?: () => void;
}

const PING_INTERVAL = 30_000;
const MAX_RECONNECT_DELAY = 16_000;

export function createJobWebSocket(jobId: string, callbacks: WSCallbacks) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const wsUrl = apiUrl.replace(/^http/, "ws") + `/ws/${jobId}`;

  let ws: WebSocket | null = null;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let reconnectDelay = 1000;
  let stopped = false;

  function connect() {
    if (stopped) return;
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      reconnectDelay = 1000;
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ command: "ping" }));
        }
      }, PING_INTERVAL);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WSMessage;
        switch (msg.type) {
          case "progress":
            callbacks.onProgress?.(msg);
            break;
          case "completed":
            callbacks.onCompleted?.(msg);
            break;
          case "error":
            callbacks.onError?.(msg);
            break;
          case "log":
            callbacks.onLog?.(msg);
            break;
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      cleanup();
      if (!stopped) {
        callbacks.onDisconnect?.();
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
      }
    };

    ws.onerror = () => {
      ws?.close();
    };
  }

  function cleanup() {
    if (pingTimer) {
      clearInterval(pingTimer);
      pingTimer = null;
    }
  }

  function close() {
    stopped = true;
    cleanup();
    if (ws) {
      ws.onclose = null;
      ws.close();
      ws = null;
    }
  }

  connect();

  return { close };
}
