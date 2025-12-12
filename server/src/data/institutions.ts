import { and, desc, eq, ilike, or, sql } from "drizzle-orm";
import db from ".";
import { catalogues, institutions } from "./schema";

export interface InstitutionListOptions {
  limit?: number;
  offset?: number;
  search?: string;
  url?: string;
}

export function sortInstitutionsByUrlMatch<
  T extends { domains: string[]; name: string },
>(institutionsList: T[], url?: string) {
  if (!url) return institutionsList;

  let hostname: string;
  try {
    hostname = new URL(url).hostname.replace(/^www\./, "").toLowerCase();
  } catch {
    return institutionsList;
  }

  const bestMatch = (institution: T): readonly [number, number] => {
    let bestScore = 0;
    let bestLength = 0;

    for (const rawDomain of institution.domains) {
      const domain = rawDomain.toLowerCase();
      if (!domain) continue;

      let score = 0;
      if (hostname === domain) score = 3;
      else if (hostname.endsWith(`.${domain}`) || domain.endsWith(`.${hostname}`))
        score = 2;
      else if (hostname.includes(domain)) score = 1;

      if (score > bestScore || (score === bestScore && domain.length > bestLength)) {
        bestScore = score;
        bestLength = domain.length;
      }
    }

    return [bestScore, bestLength] as const;
  };

  return [...institutionsList].sort((a, b) => {
    const [scoreA, lengthA] = bestMatch(a);
    const [scoreB, lengthB] = bestMatch(b);
    return (
      scoreB - scoreA ||
      lengthB - lengthA ||
      a.name.localeCompare(b.name)
    );
  });
}

function normalizeDomain(domain: string) {
  return domain
    .trim()
    .replace(/^https?:\/\//, "")
    .replace(/\/.*$/, "")
    .replace(/^www\./, "")
    .toLowerCase();
}

export function normalizeDomains(domains: string[]) {
  const unique = new Set(
    domains
      .map(normalizeDomain)
      .filter((domain) => !!domain)
  );
  return Array.from(unique);
}

const domainRegex = /^(?!-)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/;

function validateDomains(domains: string[]) {
  const normalized = normalizeDomains(domains);
  const invalid = normalized.filter((domain) => !domainRegex.test(domain));
  if (invalid.length) {
    throw new Error(`Invalid domain(s): ${invalid.join(", ")}`);
  }
  if (!normalized.length) {
    throw new Error("At least one domain is required");
  }
  return normalized;
}

function buildSearchFilter(search?: string) {
  if (!search) {
    return undefined;
  }

  const like = `%${search}%`;
  return or(
    ilike(institutions.name, like),
    sql`EXISTS (
      SELECT 1 FROM unnest(${institutions.domains}) as domain
      WHERE domain ILIKE ${like}
    )`
  );
}


export async function getInstitutionCount(
  options: Omit<InstitutionListOptions, "limit" | "offset" | "url">
) {
  const { search } = options;
  const result = await db
    .select({ count: sql<number>`count(*)` })
    .from(institutions)
    .where(and(buildSearchFilter(search)));
  return result[0].count;
}

export async function findInstitutions(options: InstitutionListOptions) {
  const { limit = 20, offset = 0, search, url } = options;
  const baseQuery = db
    .select({
      institution: institutions,
      catalogueCount: sql<number>`count(${catalogues.id})`,
    })
    .from(institutions)
    .leftJoin(catalogues, eq(catalogues.institutionId, institutions.id))
    .where(and(buildSearchFilter(search)))
    .groupBy(institutions.id)
    .orderBy(desc(institutions.createdAt));

  const rows = url
    ? await baseQuery
    : await baseQuery.limit(limit).offset(offset);

  const mapped = rows.map((row) => ({
    ...row.institution,
    catalogueCount: row.catalogueCount,
  }));

  const sorted = sortInstitutionsByUrlMatch(mapped, url);
  if (url) {
    return sorted.slice(offset, offset + limit);
  }

  return sorted;
}

export async function findInstitutionById(id: number) {
  return db.query.institutions.findFirst({
    where: (inst, { eq }) => eq(inst.id, id),
    with: {
      catalogues: {
        with: {
          recipes: true,
          institution: true,
        },
        orderBy: (catalogues, { desc }) => desc(catalogues.createdAt),
      },
    },
  });
}

export async function createInstitution(name: string, domains: string[]) {
  const normalized = validateDomains(domains);
  const result = await db
    .insert(institutions)
    .values({ name, domains: normalized })
    .returning();
  return result[0];
}

export async function updateInstitution(
  id: number,
  name: string,
  domains: string[]
) {
  const normalized = validateDomains(domains);
  const result = await db
    .update(institutions)
    .set({ name, domains: normalized })
    .where(eq(institutions.id, id))
    .returning();
  return result[0];
}

export async function destroyInstitution(id: number) {
  const [{ count }] = await db
    .select({ count: sql<number>`count(*)` })
    .from(catalogues)
    .where(eq(catalogues.institutionId, id));

  if (count > 0) {
    throw new Error("Cannot delete an institution with existing catalogues.");
  }

  return db.delete(institutions).where(eq(institutions.id, id));
}
