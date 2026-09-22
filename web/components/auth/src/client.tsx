"use client";

import { signIn } from "next-auth/react";
import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
    type ReactNode,
} from "react";

export type AuthenticatedUser = {
    id: string;
    email: string;
    name: string | null;
    roles: string[];
};

export type BffAuthContextValue = {
    user: AuthenticatedUser | undefined;
    isAuthenticated: boolean;
    isLoading: boolean;
    loading: boolean;
    error: string | undefined;
    login: (
        callbackUrl?: string,
        authorizationParams?: Record<string, string>,
    ) => void;
    logout: () => Promise<void>;
    refresh: () => Promise<boolean>;
    hasRole: (role: string) => boolean;
};

const Context = createContext<BffAuthContextValue | null>(null);

type MeResult = {
    authenticated: boolean;
    user?: AuthenticatedUser;
    sessionExpired?: boolean;
};

function getCurrentCallbackUrl(): string {
    return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

export function redirectToBffHome(
    sessionExpired = false,
    logoutPath = "/api/auth/logout",
    fetcher: typeof fetch = fetch,
) {
    if (typeof window === "undefined") {
        return;
    }

    const target = sessionExpired ? "/?sessionExpired=1" : "/";

    if (!sessionExpired) {
        window.location.replace(target);
        return;
    }

    void fetcher(logoutPath, {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
    })
        .catch(() => undefined)
        .finally(() => {
            window.location.replace(target);
        });
}

async function loadCurrentUser(
    mePath: string,
    fetcher: typeof fetch,
): Promise<MeResult> {
    const response = await fetcher(mePath, {
        credentials: "same-origin",
        cache: "no-store",
    });

    if (response.status === 401) {
        const body = (await response.json().catch(() => ({}))) as {
            code?: string;
        };
        return {
            authenticated: false,
            sessionExpired: body.code === "SESSION_EXPIRED",
        };
    }

    if (!response.ok) {
        throw new Error(`Unable to load current user (${response.status})`);
    }

    return {
        authenticated: true,
        user: (await response.json()) as AuthenticatedUser,
    };
}

export function BffAuthProvider({
    children,
    logoutPath = "/api/auth/logout",
    mePath = "/api/me",
    fallback = null,
    unauthorizedBehavior = "anonymous",
    logoutCallbackUrl,
    fetcher = fetch,
}: Readonly<{
    children: ReactNode;
    logoutPath?: string;
    mePath?: string;
    fallback?: ReactNode;
    unauthorizedBehavior?: "anonymous" | "login" | "home";
    logoutCallbackUrl?: string;
    fetcher?: typeof fetch;
}>) {
    const [user, setUser] = useState<AuthenticatedUser | undefined>(undefined);
    const [isLoading, setLoading] = useState(true);
    const [error, setError] = useState<string | undefined>(undefined);
    const initialLoadRef = useRef<Promise<MeResult> | null>(null);

    const applyMeResult = useCallback(
        (result: MeResult) => {
            if (result.authenticated) {
                setUser((currentUser) => {
                    const nextUser = result.user;
                    if (!currentUser || !nextUser) {
                        return nextUser;
                    }

                    const unchanged =
                        currentUser.id === nextUser.id &&
                        currentUser.email === nextUser.email &&
                        currentUser.name === nextUser.name &&
                        currentUser.roles.length === nextUser.roles.length &&
                        currentUser.roles.every(
                            (role, index) => role === nextUser.roles[index],
                        );

                    return unchanged ? currentUser : nextUser;
                });
            } else {
                setUser(undefined);
                if (unauthorizedBehavior === "login") {
                    signIn("keycloak", {
                        callbackUrl: getCurrentCallbackUrl(),
                    });
                } else if (
                    unauthorizedBehavior === "home" &&
                    result.sessionExpired
                ) {
                    redirectToBffHome(true, logoutPath, fetcher);
                }
            }
            return result.authenticated;
        },
        [fetcher, logoutPath, unauthorizedBehavior],
    );

    const refresh = useCallback(async () => {
        // Background session refresh. Do not toggle the provider's loading state:
        // consumers use that flag for the initial auth gate, and changing it here
        // would unmount/remount the application shell every time /api/me runs.
        try {
            const authenticated = applyMeResult(
                await loadCurrentUser(mePath, fetcher),
            );
            if (authenticated) {
                setError(undefined);
            }
            return authenticated;
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
            return false;
        }
    }, [applyMeResult, mePath, fetcher]);

    useEffect(() => {
        let active = true;
        initialLoadRef.current ??= loadCurrentUser(mePath, fetcher);
        initialLoadRef.current
            .then((result) => {
                if (active) {
                    applyMeResult(result);
                }
            })
            .catch((err) => {
                if (active) {
                    setError(err instanceof Error ? err.message : String(err));
                }
            })
            .finally(() => {
                if (active) {
                    setLoading(false);
                }
            });
        return () => {
            active = false;
        };
    }, [applyMeResult, mePath, fetcher]);

    const login = useCallback(
        (
            callbackUrl?: string,
            authorizationParams?: Record<string, string>,
        ) => {
            void signIn(
                "keycloak",
                {
                    callbackUrl: callbackUrl ?? getCurrentCallbackUrl(),
                },
                authorizationParams,
            );
        },
        [],
    );

    const logout = useCallback(async () => {
        const callbackUrl = logoutCallbackUrl ?? getCurrentCallbackUrl();
        const response = await fetcher(logoutPath, {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(`Logout failed (${response.status})`);
        }
        setUser(undefined);
        window.location.replace(callbackUrl);
    }, [fetcher, logoutCallbackUrl, logoutPath]);

    const hasRole = useCallback(
        (role: string) => {
            if (!user) {
                return false;
            }
            return user.roles.includes(role);
        },
        [user],
    );

    const value = useMemo(
        () => ({
            user,
            isAuthenticated: !!user,
            isLoading,
            loading: isLoading,
            error,
            login,
            logout,
            refresh,
            hasRole,
        }),
        [user, isLoading, error, login, logout, refresh, hasRole],
    );

    return (
        <Context.Provider value={value}>
            {isLoading ? fallback : children}
        </Context.Provider>
    );
}

export function useBffAuth() {
    const value = useContext(Context);
    if (!value) {
        throw new Error("useBffAuth must be used within BffAuthProvider");
    }
    return value;
}
