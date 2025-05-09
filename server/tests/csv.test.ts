import { randomUUID } from "crypto";
import { Transform } from "stream";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CatalogueType,
  CompetencyStructuredData,
  CourseStructuredData,
  LearningProgramStructuredData,
} from "../../common/types";
import { buildCsv } from "../src/csv";
import * as datasetModule from "../src/data/datasets";
import * as extractionModule from "../src/data/extractions";

vi.mock("../src/data/datasets");
vi.mock("../src/data/extractions");
vi.mock("crypto");

describe("buildCsv", () => {
  let csvStream: Transform;
  const mockWrite = vi.fn();
  const mockEnd = vi.fn();
  const mockEmit = vi.fn();

  beforeEach(() => {
    vi.resetAllMocks();

    csvStream = {
      write: mockWrite,
      end: mockEnd,
      emit: mockEmit,
    } as unknown as Transform;

    vi.mocked(randomUUID).mockReturnValue(
      "12345678-1234-1234-1234-123456789012"
    );

    vi.resetModules();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should handle empty results and end the stream", async () => {
    vi.mocked(extractionModule.findExtractionById).mockResolvedValue({
      id: 1,
      recipe: {
        catalogue: {
          catalogueType: CatalogueType.COURSES,
        },
      },
    } as any);

    vi.mocked(datasetModule.findDataItems).mockResolvedValue({ items: [] });

    await buildCsv(csvStream, 1);

    expect(mockEnd).toHaveBeenCalled();
    expect(mockWrite).not.toHaveBeenCalled();
  });

  it("should process course data correctly", async () => {
    vi.mocked(extractionModule.findExtractionById).mockResolvedValue({
      id: 1,
      recipe: {
        catalogue: {
          catalogueType: CatalogueType.COURSES,
        },
      },
    } as any);

    const mockCourseData = {
      items: [
        {
          id: 1,
          url: "https://example.com/course1",
          structuredData: {
            course_id: "COURSE-001",
            course_name: "Test Course",
            course_description: "Course description",
            course_credits_min: 3,
            course_credits_max: undefined,
            course_credits_type: "Credit Hour",
            course_prerequisites: "None",
          } as CourseStructuredData,
          textInclusion: {
            course_name: { full: true },
            course_description: { full: true },
          },
        },
      ],
    };

    vi.mocked(datasetModule.findDataItems)
      .mockResolvedValueOnce(mockCourseData)
      .mockResolvedValueOnce({ items: [] });

    await buildCsv(csvStream, 1);

    expect(mockWrite).toHaveBeenCalledTimes(1);
    expect(mockWrite).toHaveBeenCalledWith(
      expect.objectContaining({
        "External Identifier": "COURSE-001",
        "Coded Notation": "COURSE-001",
        "Learning Type": "Course",
        "Learning Opportunity Name": "Test Course",
        Description: "Course description",
        Language: "English",
        "Life Cycle Status Type": "Active",
        "In Catalog": "https://example.com/course1",
        "Credit Unit Value": 3,
        "Credit Unit Type": "Credit Hour",
      })
    );
    expect(mockEnd).toHaveBeenCalled();
  });

  it("should process learning program data correctly", async () => {
    vi.mocked(extractionModule.findExtractionById).mockResolvedValue({
      id: 1,
      recipe: {
        catalogue: {
          catalogueType: CatalogueType.LEARNING_PROGRAMS,
        },
      },
    } as any);

    const mockLearningProgramData = {
      items: [
        {
          id: 1,
          url: "https://example.com/program1",
          structuredData: {
            learning_program_id: "PROG-001",
            learning_program_name: "Test Program",
            learning_program_description: "Program description",
          } as LearningProgramStructuredData,
          textInclusion: {
            learning_program_name: { full: true },
            learning_program_description: { full: true },
          },
        },
      ],
    };

    vi.mocked(datasetModule.findDataItems)
      .mockResolvedValueOnce(mockLearningProgramData)
      .mockResolvedValueOnce({ items: [] });

    await buildCsv(csvStream, 1);

    expect(mockWrite).toHaveBeenCalledTimes(1);
    expect(mockWrite).toHaveBeenCalledWith(
      expect.objectContaining({
        "External Identifier": "PROG-001",
        "Learning Type": "Learning Program",
        "Learning Opportunity Name": "Test Program",
        Description: "Program description",
        "Subject Webpage": "https://example.com/program1",
        Language: "English",
      })
    );
    expect(mockEnd).toHaveBeenCalled();
  });

  it("should process competency data correctly", async () => {
    vi.mocked(extractionModule.findExtractionById).mockResolvedValue({
      id: 1,
      recipe: {
        catalogue: {
          catalogueType: CatalogueType.COMPETENCIES,
        },
      },
    } as any);

    const mockCompetencyData = {
      items: [
        {
          id: 1,
          url: "https://example.com/competency1",
          structuredData: {
            competency_framework: "Test Framework",
            text: "Competency 1",
            language: "English",
          } as CompetencyStructuredData,
          textInclusion: {
            text: { full: true },
          },
        },
      ],
    };

    vi.mocked(datasetModule.findDataItems)
      .mockResolvedValueOnce(mockCompetencyData)
      .mockResolvedValueOnce({ items: [] });

    await buildCsv(csvStream, 1);

    // First write is the framework
    expect(mockWrite).toHaveBeenCalledTimes(2);
    expect(mockWrite).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        "@type": "ceasn:CompetencyFramework",
        "@id": "12345678-1234-1234-1234-123456789012",
        "ceasn:name": "Test Framework",
        "ceasn:description": expect.any(String),
        "ceasn:inLanguage": "English",
      })
    );

    // Second write is the competency
    expect(mockWrite).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        "@type": "ceasn:Competency",
        "@id": "12345678-1234-1234-1234-123456789012",
        "ceasn:competencyText": "Competency 1",
        "ceasn:inLanguage": "English",
        "ceasn:isPartOf": "12345678-1234-1234-1234-123456789012",
      })
    );

    expect(mockEnd).toHaveBeenCalled();
  });

  it("should handle duplicate IDs correctly", async () => {
    vi.mocked(extractionModule.findExtractionById).mockResolvedValue({
      id: 1,
      recipe: {
        catalogue: {
          catalogueType: CatalogueType.COURSES,
        },
      },
    } as any);

    const mockDuplicateCourseData = {
      items: [
        {
          id: 1,
          url: "https://example.com/course1",
          structuredData: {
            course_id: "COURSE-001",
            course_name: "Test Course 1",
            course_description: "Course description 1",
          } as CourseStructuredData,
          textInclusion: {
            course_name: { full: true },
          },
        },
        {
          id: 2,
          url: "https://example.com/course2",
          structuredData: {
            course_id: "COURSE-001",
            course_name: "Test Course 2",
            course_description: "Course description 2",
          } as CourseStructuredData,
          textInclusion: {
            course_name: { full: true },
          },
        },
      ],
    };

    vi.mocked(datasetModule.findDataItems)
      .mockResolvedValueOnce(mockDuplicateCourseData)
      .mockResolvedValueOnce({ items: [] });

    await buildCsv(csvStream, 1);

    expect(mockWrite).toHaveBeenCalledTimes(2);

    // First item keeps original ID
    expect(mockWrite).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        "External Identifier": "COURSE-001",
        "Learning Opportunity Name": "Test Course 1",
      })
    );

    // Second item gets a modified ID
    expect(mockWrite).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        "External Identifier": "COURSE-001-2",
        "Learning Opportunity Name": "Test Course 2",
      })
    );

    expect(mockEnd).toHaveBeenCalled();
  });

  it("should handle extraction not found error", async () => {
    vi.mocked(extractionModule.findExtractionById).mockResolvedValue(undefined);

    await buildCsv(csvStream, 1);

    expect(mockEmit).toHaveBeenCalledWith("error", expect.any(Error));
    expect(mockEnd).toHaveBeenCalled();
  });

  it("should handle database errors properly", async () => {
    vi.mocked(extractionModule.findExtractionById).mockRejectedValue(
      new Error("Database error")
    );

    await buildCsv(csvStream, 1);

    expect(mockEmit).toHaveBeenCalledWith("error", expect.any(Error));
    expect(mockEnd).toHaveBeenCalled();
  });

  it("should paginate through results with multiple batches", async () => {
    vi.mocked(extractionModule.findExtractionById).mockResolvedValue({
      id: 1,
      recipe: {
        catalogue: {
          catalogueType: CatalogueType.COURSES,
        },
      },
    } as any);

    // First batch
    const mockBatch1 = {
      items: [
        {
          id: 1,
          url: "https://example.com/course1",
          structuredData: {
            course_id: "COURSE-001",
            course_name: "Test Course 1",
          } as CourseStructuredData,
          textInclusion: {},
        },
      ],
    };

    // Second batch
    const mockBatch2 = {
      items: [
        {
          id: 2,
          url: "https://example.com/course2",
          structuredData: {
            course_id: "COURSE-002",
            course_name: "Test Course 2",
          } as CourseStructuredData,
          textInclusion: {},
        },
      ],
    };

    // Empty batch to terminate the loop
    const emptyBatch = { items: [] };

    vi.mocked(datasetModule.findDataItems)
      .mockResolvedValueOnce(mockBatch1)
      .mockResolvedValueOnce(mockBatch2)
      .mockResolvedValueOnce(emptyBatch);

    await buildCsv(csvStream, 1);

    expect(mockWrite).toHaveBeenCalledTimes(2);
    expect(datasetModule.findDataItems).toHaveBeenCalledTimes(3);
    expect(datasetModule.findDataItems).toHaveBeenNthCalledWith(
      1,
      1,
      100,
      0,
      true
    );
    expect(datasetModule.findDataItems).toHaveBeenNthCalledWith(
      2,
      1,
      100,
      100,
      true
    );
    expect(datasetModule.findDataItems).toHaveBeenNthCalledWith(
      3,
      1,
      100,
      200,
      true
    );
    expect(mockEnd).toHaveBeenCalled();
  });
});
