import { getClientCsrfToken } from "@/security/csrfClient";

/**
 * Fetches an xTRA BFF endpoint with the double-submit CSRF token on every
 * request, including GET/HEAD. The CSRF bootstrap endpoint itself must use
 * the native fetch API because it is how the token is obtained.
 */
export async function bffFetch(
    input: RequestInfo | URL,
    init: RequestInit = {},
): Promise<Response> {
    const csrfToken = await getClientCsrfToken();
    const headers = new Headers(init.headers);
    headers.set("X-CSRF-Token", csrfToken);

    return fetch(input, {
        ...init,
        headers,
        credentials: "same-origin",
    });
}
