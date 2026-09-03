import { PageType, UrlPatternType } from "../../../common/types";

/** JSON schema fragment for agent-authored recipe configuration (stage 3). */
export const AGENT_RECIPE_CONFIGURATION_JSON_SCHEMA = {
  type: "object",
  required: ["pageType"],
  properties: {
    pageType: {
      type: "string",
      enum: [
        PageType.DETAIL,
        PageType.CATEGORY_LINKS,
        PageType.DETAIL_LINKS,
      ],
      description:
        "What kind of page this level is. The deepest level must be DETAIL.",
    },
    linkRegexp: {
      type: "string",
      description:
        "JavaScript RegExp pattern matching links to follow. Required for CATEGORY_LINKS and DETAIL_LINKS.",
    },
    clickSelector: {
      type: "string",
      description:
        "CSS selector for dynamic catalogue click discovery. Only when links need a click to reveal URLs.",
    },
    clickOptions: {
      type: "object",
      properties: {
        limit: {
          type: "number",
          description: "Max clickable elements to process (default 300).",
        },
        waitMs: {
          type: "number",
          description: "Max wait for page/selector in milliseconds.",
        },
      },
    },
    pagination: {
      type: "object",
      required: ["urlPatternType", "urlPattern", "totalPages"],
      properties: {
        urlPatternType: {
          type: "string",
          enum: [UrlPatternType.page_num, UrlPatternType.offset],
        },
        urlPattern: {
          type: "string",
          description:
            "Full paginated URL with {page_num} or {offset} placeholder.",
        },
        totalPages: { type: "number" },
        startPage: {
          type: "number",
          description: "First page number (default 1; use 0 for zero-based).",
        },
      },
    },
    exactLinkPatternMatch: {
      type: "boolean",
      description:
        "Use only the regexp-matched URL segment when enqueuing. Off unless duplicate path segments appear.",
    },
    pageLoadWaitTime: {
      type: "number",
      description: "Extra seconds to wait after page load before processing.",
    },
    links: {
      description: "Nested configuration for the next recipe level.",
      $ref: "#",
    },
  },
} as const;

export const AGENT_RECIPE_STAGE_NAMES = {
  1: "Assess catalogue usability",
  2: "Map catalogue structure",
  3: "Write recipe configuration",
  4: "Verify recipe",
} as const;

export type AgentRecipeStage = keyof typeof AGENT_RECIPE_STAGE_NAMES;
