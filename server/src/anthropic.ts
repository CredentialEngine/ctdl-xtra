import Anthropic from "@anthropic-ai/sdk";
import { findSetting } from "./data/settings";

export async function findAnthropicApiKey() {
  const envKey = process.env.ANTHROPIC_API_KEY?.trim();
  if (envKey) {
    return envKey;
  }
  const dbSetting = await findSetting<string>("ANTHROPIC_API_KEY", true);
  if (!dbSetting?.value) {
    throw new Error("Anthropic API Key not found");
  }
  return dbSetting.value;
}

export async function getAnthropic() {
  const apiKey = await findAnthropicApiKey();
  return new Anthropic({ apiKey });
}

export function textFromAnthropicMessage(message: Anthropic.Message): string {
  return message.content
    .flatMap((block) => (block.type === "text" ? [block.text] : []))
    .join("\n")
    .trim();
}
