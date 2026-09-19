import type { Metadata } from "next";
import type { ReactNode } from "react";
import "@/main.css";
import Providers from "./providers";
import ClientApp from "@/client-app";

export const metadata: Metadata = {
    title: "CTDL xTRA",
    description: "eXtensible Extract and Transformation Assistant",
    icons: { icon: "/logo.png" },
};

export default function RootLayout({
    children,
}: Readonly<{ children: ReactNode }>) {
    return (
        <html lang="en">
            <body>
                <Providers>
                    <ClientApp>{children}</ClientApp>
                </Providers>
            </body>
        </html>
    );
}
