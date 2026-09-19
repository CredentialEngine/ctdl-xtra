"use client";

import { BffAuthProvider } from "@credentialengine/auth/client";
import { Suspense } from "react";
import { AnalyticsWithConfig } from "./components/Analytics";
import { XtraAuthProvider } from "./components/auth/AuthProvider";
import { ConfigContextProvider } from "./components/providers/ConfigProvider";
import ThemeRegistry from "./themeRegistry";
import { SnackbarProvider } from "@/components/ui/snackbar-provider";

export default function Providers({ children }: { children: React.ReactNode }) {
    return (
        <ConfigContextProvider>
            <ThemeRegistry>
                <BffAuthProvider unauthorizedBehavior="anonymous">
                    <XtraAuthProvider>
                        <SnackbarProvider>
                            <Suspense fallback={null}>
                                <AnalyticsWithConfig />
                            </Suspense>
                            {children}
                        </SnackbarProvider>
                    </XtraAuthProvider>
                </BffAuthProvider>
            </ThemeRegistry>
        </ConfigContextProvider>
    );
}
