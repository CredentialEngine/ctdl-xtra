import "dotenv/config";
import {
  AGENT_SMOKE_URL,
  agentTargetUrl,
  inspectPagePrompt,
  runBrowserAgent,
} from "..";

async function main() {
  const apiKey = process.env.ANTHROPIC_API_KEY?.trim();
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY is required");
    process.exit(1);
  }

  const url = agentTargetUrl(process.argv[2] || AGENT_SMOKE_URL);
  const result = await runBrowserAgent({
    apiKey,
    prompt: inspectPagePrompt({ url }),
    browser: { skipProxy: !process.env.PROXY_URL },
    onEvent: (event) => console.log(`${event.type}: ${event.message}`),
  });

  console.log(
    JSON.stringify(
      {
        ok: true,
        url,
        resultText: result.resultText,
        toolNames: result.toolNames,
        numTurns: result.numTurns,
        totalCostUsd: result.totalCostUsd,
      },
      null,
      2
    )
  );
}

main().catch((err) => {
  console.error(err instanceof Error ? err.stack || err.message : err);
  process.exit(1);
});
