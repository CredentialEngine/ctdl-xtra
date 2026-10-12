import { beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_EXTRACTION_MODEL } from "../../common/modelMetadata";
import { ProviderModel } from "../../common/types";

const findSetting = vi.fn();

vi.mock("../src/data/settings", () => ({
  findSetting: (...args: unknown[]) => findSetting(...args),
}));

import { resolveExtractionModel } from "../src/extraction/defaultExtractionModel";

describe("resolveExtractionModel", () => {
  beforeEach(() => {
    findSetting.mockReset();
  });

  it("uses an explicit model without reading settings", async () => {
    await expect(resolveExtractionModel(ProviderModel.ClaudeHaiku45)).resolves.toBe(
      ProviderModel.ClaudeHaiku45
    );
    expect(findSetting).not.toHaveBeenCalled();
  });

  it("uses the saved default when an extraction is started without a model", async () => {
    findSetting.mockResolvedValue({ value: ProviderModel.ClaudeSonnet5 });
    await expect(resolveExtractionModel()).resolves.toBe(
      ProviderModel.ClaudeSonnet5
    );
    expect(findSetting).toHaveBeenCalledWith("DEFAULT_EXTRACTION_MODEL");
  });

  it("falls back to the built-in default when no setting is stored", async () => {
    findSetting.mockResolvedValue(null);
    await expect(resolveExtractionModel()).resolves.toBe(DEFAULT_EXTRACTION_MODEL);
  });

  it("falls back when the stored value is not a known model", async () => {
    findSetting.mockResolvedValue({ value: "not-a-model" });
    await expect(resolveExtractionModel()).resolves.toBe(DEFAULT_EXTRACTION_MODEL);
  });
});
