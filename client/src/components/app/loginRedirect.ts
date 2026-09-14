export const LOGIN_PATH = "/";
export const LOGOUT_PATH = "/logout";
export const REDIRECT_PARAM = "redirect";

const SAME_ORIGIN_BASE = "https://xtra.invalid";

function isPathWithOptionalQuery(value: string, path: string) {
  return value === path || value.startsWith(`${path}?`);
}

function pathAndSearchFrom(value: string) {
  try {
    const url = new URL(value, SAME_ORIGIN_BASE);
    return `${url.pathname}${url.search}`;
  } catch {
    return undefined;
  }
}

export function currentPathWithSearch() {
  return `${window.location.pathname}${window.location.search}`;
}

export function loginPathWithReturnTo(returnTo: string) {
  const hasReturnTo = Boolean(returnTo);
  const isAlreadyOnLogin = returnTo === LOGIN_PATH;
  const shouldOmitRedirect = !hasReturnTo || isAlreadyOnLogin;

  if (shouldOmitRedirect) {
    return LOGIN_PATH;
  }

  return `${LOGIN_PATH}?${REDIRECT_PARAM}=${encodeURIComponent(returnTo)}`;
}

export function safeReturnTo(value: string | null) {
  const pathAndSearch = value ? pathAndSearchFrom(value) : undefined;
  const isRootRelative = pathAndSearch?.startsWith("/") === true;
  const isLoginPath =
    !!pathAndSearch && isPathWithOptionalQuery(pathAndSearch, LOGIN_PATH);
  const isLogoutPath =
    !!pathAndSearch && isPathWithOptionalQuery(pathAndSearch, LOGOUT_PATH);
  const isInAppPath = isRootRelative && !isLoginPath && !isLogoutPath;

  if (!isInAppPath) {
    return undefined;
  }

  return pathAndSearch;
}

export function safeReturnToFromSearch(search: string) {
  return safeReturnTo(new URLSearchParams(search).get(REDIRECT_PARAM));
}
