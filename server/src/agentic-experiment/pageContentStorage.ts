import { constants } from "fs";
import { access, mkdir, writeFile } from "fs/promises";
import path from "path";
import { errorStyled } from "./agentLogColors";
import type { RegisteredPage } from "./pageRegistry";

export function encodeUrlForFilename(url: string): string {
  return Buffer.from(url, "utf8").toString("base64url");
}

export function buildAgenticExtractionPagesDir(csvPath: string): string {
  return path.join(
    path.dirname(csvPath),
    path.basename(csvPath, path.extname(csvPath))
  );
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

export async function resolveRegisteredPageContentPath(
  extractionDir: string,
  url: string
): Promise<string> {
  const encodedUrl = encodeUrlForFilename(url);
  const basePath = path.join(extractionDir, encodedUrl);
  const primaryPath = `${basePath}.txt`;

  if (!(await fileExists(primaryPath))) {
    return primaryPath;
  }

  for (let suffix = 1; ; suffix += 1) {
    const candidate = `${basePath}-${suffix}.txt`;
    if (!(await fileExists(candidate))) {
      return candidate;
    }
  }
}

export async function writeRegisteredPageContent(options: {
  extractionDir: string;
  page: RegisteredPage;
}): Promise<string> {
  await mkdir(options.extractionDir, { recursive: true });
  const filePath = await resolveRegisteredPageContentPath(
    options.extractionDir,
    options.page.url
  );
  await writeFile(filePath, options.page.content, "utf8");
  return filePath;
}

/** Fire-and-forget — safe to call from sync MCP tool callbacks. */
export function saveRegisteredPageContent(options: {
  extractionDir: string;
  page: RegisteredPage;
}): void {
  void writeRegisteredPageContent(options).catch((error) => {
    errorStyled(
      "error",
      `Failed to save page content for ${options.page.url}: ${String(error)}`
    );
  });
}
