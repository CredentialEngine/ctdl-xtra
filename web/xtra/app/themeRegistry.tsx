"use client";

import createCache from "@emotion/cache";
import { CacheProvider } from "@emotion/react";
import { CssBaseline } from "@mui/material";
import { ThemeProvider } from "@mui/material/styles";
import { ConfigProvider as AntConfigProvider, theme as antTheme } from "antd";
import { useServerInsertedHTML } from "next/navigation";
import {
    createContext,
    useContext,
    useEffect,
    useMemo,
    useState,
    useSyncExternalStore,
} from "react";

import { applyColorSchemeVariables, createAppTheme } from "./theme";

const ThemeModeContext = createContext<{ mode: "light" | "dark" } | null>(null);

export function useThemeMode() {
    const value = useContext(ThemeModeContext);
    if (!value)
        throw new Error("useThemeMode must be used inside ThemeRegistry");
    return value;
}

function subscribe(callback: () => void) {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    mql.addEventListener("change", callback);
    return () => mql.removeEventListener("change", callback);
}

function useIsDarkMode() {
    return useSyncExternalStore(
        subscribe,
        () => window.matchMedia("(prefers-color-scheme: dark)").matches,
        () => false,
    );
}

export default function ThemeRegistry({
    children,
}: Readonly<{ children: React.ReactNode }>) {
    const prefersDark = useIsDarkMode();
    const mode: "light" | "dark" = prefersDark ? "dark" : "light";
    const theme = useMemo(() => createAppTheme(mode), [mode]);

    useEffect(() => {
        // Appearance follows the operating-system/browser color-scheme preference only.
        applyColorSchemeVariables(mode);
    }, [mode]);

    const [{ cache, flush }] = useState(() => {
        const cache = createCache({ key: "mui" });
        cache.compat = true;
        const prevInsert = cache.insert;
        let inserted: string[] = [];
        cache.insert = (...args) => {
            const serialized = args[1];
            if (cache.inserted[serialized.name] === undefined)
                inserted.push(serialized.name);
            return prevInsert(...args);
        };
        const flush = () => {
            const prevInserted = inserted;
            inserted = [];
            return prevInserted;
        };
        return { cache, flush };
    });

    useServerInsertedHTML(() => {
        const names = flush();
        if (names.length === 0) return null;
        let styles = "";
        for (const name of names) styles += cache.inserted[name];
        return (
            <style
                key={cache.key}
                data-emotion={`${cache.key} ${names.join(" ")}`}
                dangerouslySetInnerHTML={{ __html: styles }}
            />
        );
    });

    return (
        <ThemeModeContext.Provider value={{ mode }}>
            <CacheProvider value={cache}>
                <ThemeProvider theme={theme}>
                    <CssBaseline />
                    <AntConfigProvider
                        theme={{
                            algorithm:
                                mode === "dark"
                                    ? antTheme.darkAlgorithm
                                    : antTheme.defaultAlgorithm,
                            token: {
                                colorPrimary:
                                    mode === "dark" ? "#99F3F0" : "#0A2942",
                                colorBgBase:
                                    mode === "dark" ? "#07131D" : "#FFFFFF",
                                colorBgContainer:
                                    mode === "dark" ? "#102332" : "#FFFFFF",
                                colorBgElevated:
                                    mode === "dark" ? "#172F41" : "#FFFFFF",
                                colorFillAlter:
                                    mode === "dark" ? "#17384C" : "#F7F9FA",
                                colorText:
                                    mode === "dark" ? "#FFFFFF" : "#0A2942",
                                colorTextSecondary:
                                    mode === "dark" ? "#E7EEF3" : "#314A5E",
                                colorBorder:
                                    mode === "dark" ? "#355367" : "#C4CDD4",
                                colorBorderSecondary:
                                    mode === "dark" ? "#29475A" : "#D2D9DE",
                                borderRadius: 8,
                                fontFamily: theme.typography.fontFamily,
                            },
                            components: {
                                Table: {
                                    headerBg:
                                        mode === "dark" ? "#17384C" : "#F7F9FA",
                                    headerColor:
                                        mode === "dark" ? "#FFFFFF" : "#0A2942",
                                    headerSortActiveBg:
                                        mode === "dark" ? "#1D465E" : "#EEF3F6",
                                    headerSortHoverBg:
                                        mode === "dark" ? "#214E67" : "#E8EEF2",
                                    rowHoverBg:
                                        mode === "dark" ? "#17384C" : "#F7F9FA",
                                    borderColor:
                                        mode === "dark" ? "#29475A" : "#D2D9DE",
                                },
                                Pagination: {
                                    itemBg:
                                        mode === "dark" ? "#102332" : "#FFFFFF",
                                },
                            },
                        }}
                    >
                        {children}
                    </AntConfigProvider>
                </ThemeProvider>
            </CacheProvider>
        </ThemeModeContext.Provider>
    );
}
