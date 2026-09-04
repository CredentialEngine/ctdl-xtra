/** User-facing labels for Anthropic / Claude Agent SDK model slugs and API IDs. */
const ANTHROPIC_MODEL_LABELS: Record<string, string> = {
  // Agent SDK short aliases
  haiku: "Haiku",
  sonnet: "Sonnet",
  opus: "Opus",
  fable: "Fable",

  // Current generation (API IDs and aliases)
  "claude-fable-5-1": "Fable 5.1",
  "claude-opus-5": "Opus 5",
  "claude-sonnet-5": "Sonnet 5",
  "claude-haiku-4-5": "Haiku 4.5",
  "claude-haiku-4-5-20251001": "Haiku 4.5",

  // Legacy / prior generation
  "claude-fable-5": "Fable 5",
  "claude-opus-4-8": "Opus 4.8",
  "claude-opus-4-7": "Opus 4.7",
  "claude-opus-4-6": "Opus 4.6",
  "claude-opus-4-5": "Opus 4.5",
  "claude-opus-4-1": "Opus 4.1",
  "claude-opus-4-0": "Opus 4",
  "claude-sonnet-4-6": "Sonnet 4.6",
  "claude-sonnet-4-5": "Sonnet 4.5",
  "claude-sonnet-4-0": "Sonnet 4",
  "claude-3-7-sonnet": "Sonnet 3.7",
  "claude-3-7-sonnet-20250219": "Sonnet 3.7",
  "claude-3-5-sonnet": "Sonnet 3.5",
  "claude-3-5-sonnet-20241022": "Sonnet 3.5",
  "claude-3-5-sonnet-20240620": "Sonnet 3.5",
  "claude-3-5-haiku": "Haiku 3.5",
  "claude-3-5-haiku-20241022": "Haiku 3.5",
  "claude-3-opus": "Opus 3",
  "claude-3-opus-20240229": "Opus 3",
  "claude-3-sonnet": "Sonnet 3",
  "claude-3-sonnet-20240229": "Sonnet 3",
  "claude-3-haiku": "Haiku 3",
  "claude-3-haiku-20240307": "Haiku 3",
  "claude-2-1": "Claude 2.1",
  "claude-2-0": "Claude 2",
  "claude-instant-1-2": "Claude Instant 1.2",
};

function normalizeAnthropicModelKey(model: string): string {
  return model.trim().toLowerCase();
}

function stripSnapshotDateSuffix(model: string): string {
  return model.replace(/-\d{8}$/, "");
}

function titleCaseAnthropicSlug(model: string): string {
  const slug = model.replace(/^claude-/, "");
  if (!slug) {
    return model;
  }
  return slug
    .split("-")
    .filter(Boolean)
    .map((part) => {
      if (/^\d/.test(part) && part.includes(".")) {
        return part;
      }
      if (/^\d+$/.test(part)) {
        return part;
      }
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join(" ");
}

/** Map an Anthropic model slug or API ID to a user-friendly label. */
export function anthropicModelLabel(model: string): string {
  const key = normalizeAnthropicModelKey(model);
  if (!key) {
    return model;
  }

  const direct = ANTHROPIC_MODEL_LABELS[key];
  if (direct) {
    return direct;
  }

  const withoutDate = stripSnapshotDateSuffix(key);
  const dated = ANTHROPIC_MODEL_LABELS[withoutDate];
  if (dated) {
    return dated;
  }

  if (key.startsWith("claude-")) {
    return titleCaseAnthropicSlug(key);
  }

  return titleCaseAnthropicSlug(key);
}
