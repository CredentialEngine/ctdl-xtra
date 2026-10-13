import { existsSync } from "fs";
import path from "path";
import { serverPackageRoot } from "./paths";

export function monorepoCommonTypesPath(root = serverPackageRoot()): string {
  return path.join(root, "..", "common", "types.ts");
}

export function compiledCommonTypesPath(root = serverPackageRoot()): string {
  return path.join(root, "dist", "common", "types.js");
}

/** Docker/prod layout: built `dist/common`, no sibling source `common/`. */
export function agentMcpPrefersCompiledEntry(root = serverPackageRoot()): boolean {
  return (
    existsSync(compiledCommonTypesPath(root)) &&
    !existsSync(monorepoCommonTypesPath(root))
  );
}

export function mergeMcpSubprocessEnv(
  overrides: Record<string, string>
): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined) {
      env[key] = value;
    }
  }
  return { ...env, ...overrides };
}

export function resolveAgentMcpCommand(
  serverFileName: string,
  compiledDir: string
): { command: string; args: string[] } {
  const root = serverPackageRoot();
  const sourceEntry = path.join(root, "src", "agentic", `${serverFileName}.ts`);
  const tsxCli = path.join(root, "node_modules", "tsx", "dist", "cli.mjs");
  const compiledEntry = path.join(compiledDir, `${serverFileName}.js`);

  if (
    agentMcpPrefersCompiledEntry(root) &&
    existsSync(compiledEntry)
  ) {
    return { command: process.execPath, args: [compiledEntry] };
  }

  if (
    existsSync(monorepoCommonTypesPath(root)) &&
    existsSync(sourceEntry) &&
    existsSync(tsxCli)
  ) {
    return { command: process.execPath, args: [tsxCli, sourceEntry] };
  }

  if (existsSync(compiledEntry)) {
    return { command: process.execPath, args: [compiledEntry] };
  }

  if (existsSync(sourceEntry) && existsSync(tsxCli)) {
    return { command: process.execPath, args: [tsxCli, sourceEntry] };
  }

  throw new Error(
    `Could not resolve MCP entry for ${serverFileName} (run pnpm run build in server/)`
  );
}
