import { OpenAI } from "openai";
import { findSetting } from "./data/settings";

export async function findOpenAiApiKey() {
  const envKey = process.env.OPENAI_API_KEY?.trim();
  if (envKey) {
    return envKey;
  }
  const dbSetting = await findSetting<string>("OPENAI_API_KEY", true);
  if (!dbSetting?.value) {
    throw new Error("OpenAI API Key not found");
  }
  return dbSetting.value;
}

export async function getOpenAi() {
  const apiKey = await findOpenAiApiKey();
  return new OpenAI({ apiKey });
}
