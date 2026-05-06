import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";

export const PAGE_REGISTRY_MCP_SERVER = "xtra";
export const REGISTER_PAGE_CONTENT_TOOL = "registerPageContent";
export const REGISTER_PAGE_CONTENT_MCP_TOOL = `mcp__${PAGE_REGISTRY_MCP_SERVER}__${REGISTER_PAGE_CONTENT_TOOL}`;

export interface RegisteredPage {
  url: string;
  title: string | null;
  content: string;
}

export class PageRegistry {
  private readonly pages = new Map<string, RegisteredPage>();

  register(page: RegisteredPage) {
    if (!page.url?.trim()) {
      throw new Error("url is required");
    }
    if (typeof page.content !== "string" || !page.content.trim()) {
      throw new Error("content is required");
    }

    this.pages.set(page.url, {
      url: page.url,
      title: page.title?.trim() || null,
      content: page.content,
    });
  }

  list(): RegisteredPage[] {
    return [...this.pages.values()];
  }

  count() {
    return this.pages.size;
  }

  discardContent(url: string) {
    const page = this.pages.get(url);
    if (!page) {
      return;
    }

    this.pages.set(url, {
      url: page.url,
      title: page.title,
      content: "",
    });
  }
}

export function createPageRegistryMcpServer(
  registry: PageRegistry,
  options?: {
    /** Sync only — must not block; the MCP tool returns immediately after this runs. */
    onRegistered?: (page: RegisteredPage) => void;
  }
) {
  return createSdkMcpServer({
    name: PAGE_REGISTRY_MCP_SERVER,
    version: "1.0.0",
    alwaysLoad: true,
    tools: [
      tool(
        REGISTER_PAGE_CONTENT_TOOL,
        "Register the full visible text collected from a crawled page. Call this once per page after navigating with Puppeteer. Pass url, optional title, and content as separate structured tool fields — not a JSON string in the content field.",
        {
          url: z.string().describe("Canonical URL of the page whose content is being registered"),
          title: z
            .string()
            .optional()
            .describe("Page title if available, otherwise omit"),
          content: z
            .string()
            .describe("Full visible page text copied as-is from the page"),
        },
        async ({ url, title, content }) => {
          const page = { url, title: title ?? null, content };
          registry.register(page);
          options?.onRegistered?.(page);
          return {
            content: [
              {
                type: "text",
                text: `Registered page ${registry.count()}: ${url}`,
              },
            ],
          };
        },
        { alwaysLoad: true }
      ),
    ],
  });
}
