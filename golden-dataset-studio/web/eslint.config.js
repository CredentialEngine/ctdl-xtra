import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

// CODE-STYLE: short functions, shallow nesting. Files that still break the limits are listed in
// eslint-suppressions.json; that list may only shrink (`npm run lint` fails on stale entries).
export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { parser: tseslint.parser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    ignores: ["src/**/*.test.{ts,tsx}"],
    rules: {
      "max-lines-per-function": ["error", { max: 15, skipBlankLines: true, skipComments: true, IIFEs: true }],
      "max-depth": ["error", 3],
    },
  },
);
