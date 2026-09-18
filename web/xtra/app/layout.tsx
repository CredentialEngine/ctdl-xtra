import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Geist } from "next/font/google";
import "@/main.css";
import Providers from "./providers";
import ClientApp from "@/client-app";

const geistSans = Geist({
    variable: "--font-geist-sans",
    subsets: ["latin"],
    preload: false,
});

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
            <body className={geistSans.variable}>
                <Providers>
                    <ClientApp>{children}</ClientApp>
                </Providers>
            </body>
        </html>
    );
}
