import { describe, expect, it, vi } from "vitest";
import { CatalogueType, TextInclusion } from "../../common/types";
import { runEntityExtraction } from "../src/extraction/runEntityExtraction";
import type { DefaultLlmPageOptions } from "../src/extraction/llm";
import type { SimplifiedMarkdown } from "../src/types";

vi.mock("../src/extraction/llm/determinePresenceOfEntity", () => ({
  determinePresenceOfEntity: vi.fn(),
}));

vi.mock("../src/extraction/llm/extractAndVerifyEntityData", () => ({
  extractAndVerifyEntityData: vi.fn(),
}));

import { determinePresenceOfEntity } from "../src/extraction/llm/determinePresenceOfEntity";
import { extractAndVerifyEntityData } from "../src/extraction/llm/extractAndVerifyEntityData";

const determinePresenceOfEntityMock = vi.mocked(determinePresenceOfEntity);
const extractAndVerifyEntityDataMock = vi.mocked(extractAndVerifyEntityData);

const textInclusion = {} as TextInclusion<any>;

async function* yieldVerified(
  entities: Array<{ entity: Record<string, any> }>
) {
  for (const item of entities) {
    yield { entity: item.entity, textInclusion };
  }
}

function pageOptions(
  catalogueType: CatalogueType
): DefaultLlmPageOptions {
  return {
    url: "https://example.edu/page",
    content: "# page" as SimplifiedMarkdown,
    screenshot: "",
    catalogueType,
  };
}

describe("runEntityExtraction", () => {
  it("yields nothing when the presence check fails", async () => {
    determinePresenceOfEntityMock.mockResolvedValue({
      prompt: "presence",
      present: false,
    });

    const entries = [];
    for await (const entry of runEntityExtraction(
      pageOptions(CatalogueType.COMPETENCIES)
    )) {
      entries.push(entry);
    }

    expect(entries).toEqual([]);
    expect(extractAndVerifyEntityDataMock).not.toHaveBeenCalled();
  });

  it("flattens entity.items into individual entries", async () => {
    extractAndVerifyEntityDataMock.mockReturnValue(
      yieldVerified([
        {
          entity: {
            items: [{ course_id: "A" }, { course_id: "B" }],
          },
        },
      ])
    );

    const entries = [];
    for await (const entry of runEntityExtraction(
      pageOptions(CatalogueType.COURSES)
    )) {
      entries.push(entry.entity);
    }

    expect(entries).toEqual([{ course_id: "A" }, { course_id: "B" }]);
  });
});
