#!/usr/bin/env node
// xTRA evaluation harness
// Usage: node run.mjs <slug> <url-or-htmlfile> [--config <id>|all]

import fs from "node:fs";
import path from "node:path";
import { parseArgs } from "node:util";
import Anthropic from "@anthropic-ai/sdk";
import { prepareSource } from "./simplify.mjs";
import { buildXtraPrompt, XTRA_CONFIGS } from "./xtra-prompts.mjs";
import {
  ENHANCED_SCHEMA,
  ENHANCED_SYSTEM,
  buildEnhancedPrompt,
} from "./enhanced-schema.mjs";

if (!process.env.ANTHROPIC_API_KEY && !process.env.ANTHROPIC_AUTH_TOKEN) {
  console.error("Set ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) to run.");
  process.exit(1);
}
const client = new Anthropic();
const MODEL = process.env.CLAUDE_MODEL || "claude-opus-4-5";

// Config registry — one entry per extraction variant. Add here to add a variant.
const CONFIGS = {
  baseline_credential: {
    schema: XTRA_CONFIGS.credential.schema,
    toolName: "result",
    buildPrompt: (p) => buildXtraPrompt({ ...XTRA_CONFIGS.credential, ...p }),
  },
  baseline_learning_program: {
    schema: XTRA_CONFIGS.learning_program.schema,
    toolName: "result",
    buildPrompt: (p) => buildXtraPrompt({ ...XTRA_CONFIGS.learning_program, ...p }),
  },
  enhanced: {
    system: ENHANCED_SYSTEM,
    schema: ENHANCED_SCHEMA,
    toolName: "extract_ctdl",
    buildPrompt: buildEnhancedPrompt,
  },
};

async function runConfig(id, cfg, page) {
  const t0 = Date.now();
  const msg = await client.messages.create({
    model: MODEL,
    max_tokens: 8096,
    system: cfg.system,
    tools: [
      {
        name: cfg.toolName,
        description: "Return the extracted structured data.",
        input_schema: cfg.schema,
      },
    ],
    tool_choice: { type: "tool", name: cfg.toolName },
    messages: [{ role: "user", content: cfg.buildPrompt(page) }],
  });
  const toolUse = msg.content.find((b) => b.type === "tool_use");
  return {
    id,
    result: toolUse?.input ?? null,
    usage: msg.usage,
    latencyMs: Date.now() - t0,
    stopReason: msg.stop_reason,
  };
}

function summarize(r) {
  const n = r.result?.items?.length ?? (r.result ? 1 : 0);
  return `${r.id}: ${n} item(s), ${r.usage?.input_tokens}→${r.usage?.output_tokens} tok, ${r.latencyMs}ms`;
}

async function main() {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: { config: { type: "string", default: "all" } },
  });
  const [slug, src] = positionals;
  if (!slug || !src) {
    console.error("usage: node run.mjs <slug> <url-or-htmlfile> [--config <id>|all]");
    process.exit(1);
  }

  const page = await prepareSource(slug, src);
  console.error(`[${slug}] markdown ${page.content.length} chars from ${page.url}`);

  const ids =
    values.config === "all" ? Object.keys(CONFIGS) : values.config.split(",");
  const unknown = ids.filter((id) => !CONFIGS[id]);
  if (unknown.length) {
    console.error(
      `unknown --config ${unknown.join(",")}; valid: ${Object.keys(CONFIGS).join(", ")}`
    );
    process.exit(1);
  }
  const runs = await Promise.all(
    ids.map((id) => runConfig(id, CONFIGS[id], page))
  );

  const out = {
    slug,
    url: page.url,
    model: MODEL,
    sourceMarkdownChars: page.content.length,
    results: Object.fromEntries(runs.map((r) => [r.id, r.result])),
    // legacy keys expected by scoring/field-matrix
    baseline: runs.find((r) => r.id === "baseline_credential")?.result ?? null,
    enhanced: runs.find((r) => r.id === "enhanced")?.result ?? null,
    _meta: runs.map(({ id, usage, latencyMs, stopReason }) => ({
      id,
      usage,
      latencyMs,
      stopReason,
    })),
  };

  const outPath = path.join(page.dir, "extracted.json");
  fs.writeFileSync(outPath, JSON.stringify(out, null, 2));
  console.error(`[${slug}] wrote ${outPath}`);
  runs.forEach((r) => console.error(`  ${summarize(r)}`));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
