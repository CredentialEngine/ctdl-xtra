import { useEffect, useState } from "react";

function toStartMs(
  startTimestamp: string | number | Date | null | undefined
): number | null {
  if (startTimestamp == null || startTimestamp === "") {
    return null;
  }
  const startMs =
    startTimestamp instanceof Date
      ? startTimestamp.getTime()
      : new Date(startTimestamp).getTime();
  return Number.isFinite(startMs) ? startMs : null;
}

export function formatElapsedMs(elapsedMs: number) {
  const clamped = Math.max(0, elapsedMs);
  const elapsedHours = Math.floor(clamped / (1000 * 60 * 60));
  const elapsedMinutes = Math.floor((clamped % (1000 * 60 * 60)) / (1000 * 60));
  const elapsedSeconds = Math.floor((clamped % (1000 * 60)) / 1000);

  if (elapsedHours > 0) {
    return `${elapsedHours}hr${elapsedMinutes}mins`;
  }
  if (elapsedMinutes > 0) {
    return `${elapsedMinutes}mins`;
  }
  return `${elapsedSeconds}s`;
}

/**
 * Live elapsed time from `startTimestamp`, updated every `tickIntervalMs`.
 * Pass a non-positive interval to freeze. Returns null when there is no start.
 */
export function useTimeElapsed(
  startTimestamp: string | number | Date | null | undefined,
  tickIntervalMs: number
): string | null {
  const [nowMs, setNowMs] = useState(() => Date.now());
  const startMs = toStartMs(startTimestamp);

  useEffect(() => {
    if (startMs == null || tickIntervalMs <= 0) {
      return;
    }
    setNowMs(Date.now());
    const interval = window.setInterval(
      () => setNowMs(Date.now()),
      tickIntervalMs
    );
    return () => window.clearInterval(interval);
  }, [startMs, tickIntervalMs]);

  if (startMs == null) {
    return null;
  }
  return formatElapsedMs(nowMs - startMs);
}

/** Isolates the 1s clock so only this node re-renders while time elapses. */
export function TimeElapsedText({
  startTimestamp,
  tickIntervalMs,
}: {
  startTimestamp: string | number | Date | null | undefined;
  tickIntervalMs: number;
}) {
  return useTimeElapsed(startTimestamp, tickIntervalMs);
}
