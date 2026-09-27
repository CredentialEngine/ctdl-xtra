import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
    ...nextVitals,
    ...nextTs,
    {
        settings: {
            react: {
                version: "19.2.7",
            },
        },
        rules: {
            "@next/next/no-html-link-for-pages": "off",
        },
    },
    globalIgnores([
        "**/.next/**",
        "**/dist/**",
        "**/build/**",
        "**/coverage/**",
        "**/node_modules/**",
        "**/next-env.d.ts",
        "**/*.tsbuildinfo",
    ]),
    {
        files: ["components/**/*.{ts,tsx,js,mjs,cjs}"],
        rules: {
            "@next/next/no-html-link-for-pages": "off",
        },
    },
]);
