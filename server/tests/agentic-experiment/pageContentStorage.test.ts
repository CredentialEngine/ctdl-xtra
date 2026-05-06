import { mkdtemp, readFile, writeFile } from "fs/promises";
import os from "os";
import path from "path";
import { afterEach, describe, expect, it } from "vitest";
import {
  buildAgenticExtractionPagesDir,
  encodeUrlForFilename,
  resolveRegisteredPageContentPath,
  writeRegisteredPageContent,
} from "../../src/agentic-experiment/pageContentStorage";

describe("pageContentStorage", () => {
  const tempDirs: string[] = [];

  afterEach(async () => {
    await Promise.all(
      tempDirs.splice(0).map((dir) =>
        import("fs/promises").then(({ rm }) =>
          rm(dir, { recursive: true, force: true })
        )
      )
    );
  });

  async function makeTempDir() {
    const dir = await mkdtemp(path.join(os.tmpdir(), "agentic-pages-"));
    tempDirs.push(dir);
    return dir;
  }

  it("encodes URLs without filesystem-unsafe characters", () => {
    const encoded = encodeUrlForFilename(
      "https://example.edu/courses/abc?term=2026#outline"
    );

    expect(encoded).not.toMatch(/[/\\:?*"<>|]/);
    expect(encoded.length).toBeGreaterThan(0);
  });

  it("builds a pages directory from the CSV basename", () => {
    const csvPath = path.join(
      "/tmp/extractions",
      "antelope-course-competencies-29-05-2026-17-39.csv"
    );

    expect(buildAgenticExtractionPagesDir(csvPath)).toBe(
      "/tmp/extractions/antelope-course-competencies-29-05-2026-17-39"
    );
  });

  it("resolves numbered filenames when the primary file exists", async () => {
    const extractionDir = await makeTempDir();
    const url = "https://example.edu/courses/abc";
    const encoded = encodeUrlForFilename(url);
    const primary = path.join(extractionDir, `${encoded}.txt`);

    await writeFile(primary, "first", "utf8");

    const resolved = await resolveRegisteredPageContentPath(extractionDir, url);

    expect(resolved).toBe(path.join(extractionDir, `${encoded}-1.txt`));
  });

  it("saves registered page content under the extraction directory", async () => {
    const extractionDir = await makeTempDir();
    const page = {
      url: "https://example.edu/courses/abc",
      title: "Course ABC",
      content: "Course outline text",
    };

    const filePath = await writeRegisteredPageContent({ extractionDir, page });
    const saved = await readFile(filePath, "utf8");

    expect(saved).toBe(page.content);
  });
});
