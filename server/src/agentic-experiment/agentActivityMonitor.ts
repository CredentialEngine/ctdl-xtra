import { logStyled } from "./agentLogColors";

const DEFAULT_HEARTBEAT_SEC = 30;

export function readHeartbeatIntervalSec() {
  const value = process.env.AGENTIC_EXPERIMENT_HEARTBEAT_SEC?.trim();

  if (!value) {
    return DEFAULT_HEARTBEAT_SEC;
  }

  if (value === "off" || value === "0" || value === "false") {
    return 0;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new Error(
      "AGENTIC_EXPERIMENT_HEARTBEAT_SEC must be a non-negative number, \"off\", or \"0\" when set."
    );
  }

  return parsed;
}

export class AgentActivityMonitor {
  private lastActivityAt = Date.now();
  private lastHeartbeatLogAt = 0;
  private heartbeatTimer: ReturnType<typeof setInterval> | undefined;

  constructor(private readonly intervalSec: number) {}

  start() {
    if (this.intervalSec <= 0) {
      return;
    }

    const pollMs = Math.min(this.intervalSec * 1000, 5_000);
    this.heartbeatTimer = setInterval(() => {
      const idleSec = Math.floor((Date.now() - this.lastActivityAt) / 1000);
      if (idleSec < this.intervalSec) {
        return;
      }

      const now = Date.now();
      if (now - this.lastHeartbeatLogAt < pollMs) {
        return;
      }

      logStyled(
        "heartbeat",
        `[agent idle ${idleSec}s — session still active; waiting for model or tool]`
      );
      this.lastHeartbeatLogAt = now;
    }, pollMs);
  }

  stop() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = undefined;
    }
  }

  touch() {
    this.lastActivityAt = Date.now();
  }
}
