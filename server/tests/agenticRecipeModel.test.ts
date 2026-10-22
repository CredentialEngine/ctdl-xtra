import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_AGENTIC_RECIPE_MODEL } from "../../common/modelMetadata";
import { ProviderModel } from "../../common/types";

const findSetting = vi.fn();

vi.mock("../src/data/settings", () => ({
  findSetting: (...args: unknown[]) => findSetting(...args),
}));

import { resolveAgenticRecipeModel } from "../src/agentic/resolveAgenticRecipeModel";
import { resolveAgentModel } from "../src/agentic/types";

describe("resolveAgenticRecipeModel", () => {
  beforeEach(() => {
    findSetting.mockReset();
  });

  it("uses the saved Claude model", async () => {
    findSetting.mockResolvedValue({ value: ProviderModel.ClaudeOpus55 });
    await expect(resolveAgenticRecipeModel()).resolves.toBe(
      ProviderModel.ClaudeOpus55
    );
    expect(findSetting).toHaveBeenCalledWith("AGENTIC_RECIPE_MODEL");
  });

  it("defaults to Sonnet 5.5 when no setting is stored", async () => {
    findSetting.mockResolvedValue(null);
    await expect(resolveAgenticRecipeModel()).resolves.toBe(
      DEFAULT_AGENTIC_RECIPE_MODEL
    );
    expect(DEFAULT_AGENTIC_RECIPE_MODEL).toBe(ProviderModel.ClaudeSonnet55);
  });

  it("defaults to Sonnet 5.5 when the stored value is not a Claude model", async () => {
    findSetting.mockResolvedValue({ value: ProviderModel.Gpt6Astra });
    await expect(resolveAgenticRecipeModel()).resolves.toBe(
      ProviderModel.ClaudeSonnet55
    );
  });
});

describe("resolveAgentModel", () => {
  it("keeps an explicit model from an already queued job", () => {
    expect(resolveAgentModel("haiku")).toBe("haiku");
  });

  it("falls back to Sonnet 5.5 when a job has no model", () => {
    expect(resolveAgentModel()).toBe(ProviderModel.ClaudeSonnet55);
  });
});
