import { CatalogueType } from "../../../../common/types";
import { SimplifiedMarkdown } from "../../types";

export const MD_START = "```markdown";
export const MD_END = "```";

export interface DefaultLlmPageOptions {
  content: SimplifiedMarkdown;
  url: string;
  screenshot: string;
  catalogueType?: CatalogueType;
  logApiCalls?: {
    extractionId: number;
  };
  additionalContext?: {
    message: string;
    context?: string[];
  };
}

export function resolveAbsoluteUrl(base: string, relative: string): string {
  const baseUrl = new URL(base);
  const absoluteUrl = new URL(relative, baseUrl);
  return absoluteUrl.href;
}

// Deduplicate URLs by normalizing them while preserving query parameters and hash fragments
export function dedupUrls(urls: string[]): string[] {
  const normalizedUrls = new Set<string>();
  return urls.filter(url => {
    try {
      const normalizedUrl = new URL(url).href;
      if (normalizedUrls.has(normalizedUrl)) {
        return false;
      }
      normalizedUrls.add(normalizedUrl);
      return true;
    } catch (e) {
      console.warn(`Failed to normalize URL: ${url}`, e);
      return false;
    }
  });
};

export function filterUrlsByOrigin(urls: string[], hostname: string) {
  return urls.filter(url => {
    const urlObj = new URL(url);
    return urlObj.hostname === hostname;
  });
}
