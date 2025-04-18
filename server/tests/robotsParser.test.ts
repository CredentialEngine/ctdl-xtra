import { beforeEach, describe, expect, test, vi } from "vitest";
import { isUrlAllowed, parseRobotsTxt } from "../src/extraction/robotsParser";

// Mock the fetch function for testing
global.fetch = vi.fn();

describe("Robots.txt Parser", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  test("parseRobotsTxt should handle empty content", () => {
    const result = parseRobotsTxt("");
    expect(result.rules).toHaveLength(0);
    expect(result.sitemaps).toHaveLength(0);
  });

  test("parseRobotsTxt should handle simple robots.txt", () => {
    const content = `
      User-agent: *
      Disallow: /admin/
      Disallow: /private/
      Allow: /admin/public/
      Crawl-delay: 5
    `;

    const result = parseRobotsTxt(content);

    expect(result.rules).toHaveLength(1);
    expect(result.rules[0].userAgent).toBe("*");
    expect(result.rules[0].disallow).toContain("/admin/");
    expect(result.rules[0].disallow).toContain("/private/");
    expect(result.rules[0].allow).toContain("/admin/public/");
    expect(result.rules[0].crawlDelay).toBe(5);
  });

  test("parseRobotsTxt should handle multiple user agents", () => {
    const content = `
      User-agent: GoogleBot
      Disallow: /google/
      Crawl-delay: 10

      User-agent: BingBot
      Disallow: /bing/
      Crawl-delay: 5

      User-agent: *
      Disallow: /private/
    `;

    const result = parseRobotsTxt(content);

    expect(result.rules).toHaveLength(3);

    const googleRule = result.rules.find((r) => r.userAgent === "GoogleBot");
    expect(googleRule).toBeDefined();
    expect(googleRule?.disallow).toContain("/google/");
    expect(googleRule?.crawlDelay).toBe(10);

    const bingRule = result.rules.find((r) => r.userAgent === "BingBot");
    expect(bingRule).toBeDefined();
    expect(bingRule?.disallow).toContain("/bing/");
    expect(bingRule?.crawlDelay).toBe(5);

    const wildcardRule = result.rules.find((r) => r.userAgent === "*");
    expect(wildcardRule).toBeDefined();
    expect(wildcardRule?.disallow).toContain("/private/");
  });

  test("parseRobotsTxt should handle comments", () => {
    const content = `
      # This is a comment
      User-agent: * # This user agent applies to all
      Disallow: /admin/ # No access to admin
      Allow: / # Allow everything else
    `;

    const result = parseRobotsTxt(content);

    expect(result.rules).toHaveLength(1);
    expect(result.rules[0].userAgent).toBe("*");
    expect(result.rules[0].disallow).toContain("/admin/");
    expect(result.rules[0].allow).toContain("/");
  });

  test("parseRobotsTxt should handle sitemaps", () => {
    const content = `
      User-agent: *
      Disallow: /admin/

      Sitemap: https://example.com/sitemap.xml
      Sitemap: https://example.com/sitemap-news.xml
    `;

    const result = parseRobotsTxt(content);

    expect(result.sitemaps).toHaveLength(2);
    expect(result.sitemaps).toContain("https://example.com/sitemap.xml");
    expect(result.sitemaps).toContain("https://example.com/sitemap-news.xml");
  });

  test("isUrlAllowed should properly allow or disallow URLs", () => {
    const robotsTxt = parseRobotsTxt(`
      User-agent: *
      Disallow: /admin/
      Disallow: /private/
      Allow: /admin/public/
    `);

    // These should be allowed
    expect(isUrlAllowed(robotsTxt, "https://example.com/")).toBe(true);
    expect(isUrlAllowed(robotsTxt, "https://example.com/public")).toBe(true);
    expect(isUrlAllowed(robotsTxt, "https://example.com/admin/public/")).toBe(
      true
    );

    // These should be disallowed
    expect(isUrlAllowed(robotsTxt, "https://example.com/admin/")).toBe(false);
    expect(
      isUrlAllowed(robotsTxt, "https://example.com/admin/restricted")
    ).toBe(false);
    expect(isUrlAllowed(robotsTxt, "https://example.com/private/")).toBe(false);
  });

  test("isUrlAllowed should respect specific user agents", () => {
    const robotsTxt = parseRobotsTxt(`
      User-agent: googlebot
      Disallow: /googlebot-only/

      User-agent: *
      Disallow: /private/
    `);

    // Testing googlebot user-agent
    expect(
      isUrlAllowed(
        robotsTxt,
        "https://example.com/googlebot-only/",
        "googlebot"
      )
    ).toBe(false);
    expect(
      isUrlAllowed(robotsTxt, "https://example.com/private/", "googlebot")
    ).toBe(true);

    // Testing another user-agent
    expect(
      isUrlAllowed(robotsTxt, "https://example.com/googlebot-only/", "otherbot")
    ).toBe(true);
    expect(
      isUrlAllowed(robotsTxt, "https://example.com/private/", "otherbot")
    ).toBe(false);
  });

  test("isUrlAllowed should handle pattern wildcards", () => {
    const robotsTxt = parseRobotsTxt(`
      User-agent: *
      Disallow: /*.php$
      Disallow: /*/admin/
    `);

    // Should be disallowed
    expect(isUrlAllowed(robotsTxt, "https://example.com/page.php")).toBe(false);
    expect(isUrlAllowed(robotsTxt, "https://example.com/section/admin/")).toBe(
      false
    );

    // Should be allowed
    expect(isUrlAllowed(robotsTxt, "https://example.com/page.phps")).toBe(true);
    expect(isUrlAllowed(robotsTxt, "https://example.com/admin/")).toBe(true);
  });
});
