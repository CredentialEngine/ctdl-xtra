let cachedCsrfToken: string | undefined;
let csrfRequest: Promise<string> | null = null;

/**
 * Returns xTRA's double-submit CSRF token. The request is single-flight so
 * React Strict Mode cannot issue competing /api/csrf calls and rotate the
 * cookie underneath an already-rendered client.
 */
export function getClientCsrfToken(forceRefresh = false): Promise<string> {
    if (forceRefresh) {
        cachedCsrfToken = undefined;
        csrfRequest = null;
    }

    if (cachedCsrfToken) return Promise.resolve(cachedCsrfToken);
    if (csrfRequest) return csrfRequest;

    csrfRequest = fetch("/api/csrf", {
        credentials: "include",
        cache: "no-store",
    })
        .then(async (response) => {
            if (!response.ok) {
                throw new Error(
                    `Failed to initialize CSRF protection (HTTP ${response.status})`,
                );
            }

            const data = (await response.json()) as { csrfToken?: string };
            if (!data.csrfToken) {
                throw new Error("CSRF response did not include a token");
            }

            cachedCsrfToken = data.csrfToken;
            return data.csrfToken;
        })
        .finally(() => {
            csrfRequest = null;
        });

    return csrfRequest;
}

export function clearClientCsrfToken() {
    cachedCsrfToken = undefined;
    csrfRequest = null;
}
