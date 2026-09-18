import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Browser-facing BFF login entry point.
 *
 * The application UI never talks to Keycloak or NextAuth directly. This small
 * bridge obtains NextAuth's CSRF token from the BFF and submits the provider
 * sign-in request. OAuth tokens remain server/session concerns.
 */
export async function GET(request: NextRequest) {
    const callbackUrl = request.nextUrl.searchParams.get("callbackUrl") || "/";
    const safeCallback = callbackUrl.startsWith("/") ? callbackUrl : "/";

    const html = `<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Signing in...</title></head>
<body>
  <p>Redirecting to sign in...</p>
  <script>
    (async function () {
      try {
        const response = await fetch('/api/auth/csrf', { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok) throw new Error('Unable to initialize sign-in');
        const data = await response.json();
        const form = document.createElement('form');
        form.method = 'post';
        form.action = '/api/auth/signin/keycloak';
        const csrf = document.createElement('input');
        csrf.type = 'hidden'; csrf.name = 'csrfToken'; csrf.value = data.csrfToken;
        const callback = document.createElement('input');
        callback.type = 'hidden'; callback.name = 'callbackUrl'; callback.value = ${JSON.stringify(safeCallback)};
        form.append(csrf, callback);
        document.body.appendChild(form);
        form.submit();
      } catch (error) {
        document.body.textContent = 'Unable to start sign-in. Please return to the application and try again.';
        console.error(error);
      }
    })();
  </script>
</body>
</html>`;

    return new NextResponse(html, {
        status: 200,
        headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    });
}
