import "dotenv/config";
import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@common": path.resolve(__dirname, "../common"),
    },
  },
  test: {
    setupFiles: ["./tests/assertions.ts"],
  },
});
