const DOMAIN_REGEX = /^(?!-)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/;

export function normalizeDomain(domain: string): string {
  return domain
    .trim()
    .replace(/^https?:\/\//, "")
    .replace(/\/.*$/, "")
    .replace(/^www\./, "")
    .toLowerCase();
}

export function parseDomains(input: string): string[] {
  const parts = input
    .split(/[,\n]/)
    .map((part) => normalizeDomain(part))
    .filter(Boolean);

  return Array.from(new Set(parts));
}

export function validateDomains(domains: string[]): {
  normalized: string[];
  invalid: string[];
} {
  const normalized = Array.from(new Set(domains.map(normalizeDomain).filter(Boolean)));
  const invalid = normalized.filter((domain) => !DOMAIN_REGEX.test(domain));
  return { normalized, invalid };
}

