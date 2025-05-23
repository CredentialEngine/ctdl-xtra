import { URL } from "url";
import getLogger from "../logging";

const logger = getLogger("extraction.robotsParser");

export interface RobotsRule {
  userAgent: string;
  allow: string[];
  disallow: string[];
  crawlDelay?: number;
  sitemaps: string[];
}

export interface RobotsTxt {
  rules: RobotsRule[];
  sitemaps: string[];
}

export async function fetchAndParseRobotsTxt(
  url: string
): Promise<RobotsTxt | null> {
  try {
    const parsedUrl = new URL(url);
    const robotsUrl = `${parsedUrl.protocol}//${parsedUrl.host}/robots.txt`;

    logger.info(`Fetching robots.txt from ${robotsUrl}`);

    const response = await fetch(robotsUrl);

    if (!response.ok) {
      logger.info(`robots.txt not found at ${robotsUrl}`);
      return null;
    }

    const content = await response.text();
    return parseRobotsTxt(content);
  } catch (error) {
    logger.error(`Error fetching robots.txt: ${error}`);
    return null;
  }
}

export function parseRobotsTxt(content: string): RobotsTxt {
  const lines = content.split("\n");

  const result: RobotsTxt = {
    rules: [],
    sitemaps: [],
  };

  let currentRule: RobotsRule | null = null;

  for (let line of lines) {
    // Remove comments and trim
    const commentIndex = line.indexOf("#");
    if (commentIndex !== -1) {
      line = line.substring(0, commentIndex);
    }
    line = line.trim();

    if (!line) continue;

    // Split into field and value
    const colonIndex = line.indexOf(":");
    if (colonIndex === -1) continue;

    const field = line.substring(0, colonIndex).trim().toLowerCase();
    const value = line.substring(colonIndex + 1).trim();

    if (!value) continue;

    if (field === "user-agent") {
      // Start a new rule if we encounter a user agent
      if (
        currentRule &&
        (currentRule.allow.length > 0 ||
          currentRule.disallow.length > 0 ||
          currentRule.crawlDelay !== undefined)
      ) {
        result.rules.push(currentRule);
      }

      currentRule = {
        userAgent: value,
        allow: [],
        disallow: [],
        sitemaps: [],
      };
    } else if (field === "allow" && currentRule) {
      currentRule.allow.push(value);
    } else if (field === "disallow" && currentRule) {
      currentRule.disallow.push(value);
    } else if (field === "crawl-delay" && currentRule) {
      const delay = parseFloat(value);
      if (!isNaN(delay)) {
        currentRule.crawlDelay = delay;
      }
    } else if (field === "sitemap") {
      if (currentRule) {
        currentRule.sitemaps.push(value);
      }
      result.sitemaps.push(value);
    }
  }

  // Add the last rule if it exists
  if (
    currentRule &&
    (currentRule.allow.length > 0 ||
      currentRule.disallow.length > 0 ||
      currentRule.crawlDelay !== undefined)
  ) {
    result.rules.push(currentRule);
  }

  return result;
}

export function findRule(
  robotsTxt: RobotsTxt,
  userAgent: string = "*"
): RobotsRule | null {
  let matchingRule: RobotsRule | null = null;
  let wildcardRule: RobotsRule | null = null;

  for (const rule of robotsTxt.rules) {
    if (rule.userAgent === userAgent) {
      matchingRule = rule;
      break;
    }

    if (rule.userAgent === "*") {
      wildcardRule = rule;
    }
  }

  const rule = matchingRule || wildcardRule;

  return rule;
}

export function isUrlAllowedForRule(rule: RobotsRule, url: string): boolean {
  if (!rule || rule.disallow.length === 0) {
    return true;
  }

  const path = new URL(url).pathname;

  // Check if the URL matches any allow pattern
  for (const pattern of rule.allow) {
    if (isPathMatch(path, pattern)) {
      return true;
    }
  }

  // Check if the URL matches any disallow pattern
  for (const pattern of rule.disallow) {
    if (isPathMatch(path, pattern)) {
      return false;
    }
  }

  // Default to allowing the URL if no patterns match
  return true;
}

export function isUrlAllowed(
  robotsTxt: RobotsTxt,
  url: string,
  userAgent: string = "*"
): boolean {
  const rule = findRule(robotsTxt, userAgent);
  if (!rule) {
    return true;
  }

  return isUrlAllowedForRule(rule, url);
}

function isPathMatch(path: string, pattern: string): boolean {
  // Convert robots.txt pattern to a regular expression
  let regexPattern = pattern
    .replace(/\./g, "\\.")
    .replace(/\*/g, ".*")
    .replace(/\$/g, "$");

  // Add start anchor if pattern doesn't start with *
  if (!pattern.startsWith("*")) {
    regexPattern = "^" + regexPattern;
  }

  const regex = new RegExp(regexPattern);
  return regex.test(path);
}
