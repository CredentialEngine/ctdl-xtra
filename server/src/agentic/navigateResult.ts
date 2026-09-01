export type NavigateToolPayload =
  | { ok: true; kind: "navigate"; url: string }
  | {
      ok: false;
      kind: "proxy";
      url: string;
      status?: number | null;
      message?: string;
    };

export function formatNavigateToolResult(payload: NavigateToolPayload): string {
  const line = JSON.stringify(payload);
  if (payload.ok) {
    return `${line}\nNavigated to ${payload.url}`;
  }
  const detail =
    payload.message ||
    (payload.status === 407
      ? `HTTP 407 for ${payload.url}`
      : `Proxy request failed for ${payload.url}`);
  return `${line}\n${detail}`;
}

export function parseNavigateToolResult(
  message: string
): NavigateToolPayload | undefined {
  const text = message.replace(/^error /, "").trim();
  const firstLine = text.split("\n")[0];
  if (!firstLine) {
    return undefined;
  }
  try {
    const parsed = JSON.parse(firstLine) as NavigateToolPayload;
    if (
      parsed &&
      typeof parsed === "object" &&
      typeof parsed.ok === "boolean" &&
      (parsed.kind === "navigate" || parsed.kind === "proxy") &&
      typeof parsed.url === "string"
    ) {
      return parsed;
    }
  } catch {
    return undefined;
  }
  return undefined;
}
