import "dotenv/config";
import { Client } from "pg";
import crypto from "node:crypto";
import path from "node:path";
import { spawn } from "node:child_process";

// Vitest global setup that creates a unique ephemeral Postgres database, runs migrations,
// sets DATABASE_URL for the test process, and returns a teardown to drop the DB.
export default async function () {
  const baseUrl = process.env.DATABASE_URL;
  if (!baseUrl) {
    throw new Error("DATABASE_URL must be set to a Postgres connection string");
  }

  // Parse the base URL and derive an admin connection (to 'postgres' db) for create/drop.
  const url = new URL(baseUrl);
  const originalDbName = url.pathname.replace(/^\//, "");

  // Make a very-low-collision database name: include timestamp, random, pool id, and original.
  const rand = crypto.randomBytes(6).toString("hex");
  const poolId = process.env.VITEST_POOL_ID ?? "p0";
  const uniqueDbName = `vitest_${poolId}_${Date.now().toString(36)}_${rand}_${originalDbName}`;

  // Use admin DB for create/drop
  const adminUrl = new URL(url.toString());
  adminUrl.pathname = "/postgres";

  const adminClient = new Client({ connectionString: adminUrl.toString() });
  await adminClient.connect();
  try {
    // Create the ephemeral DB
    await adminClient.query(`CREATE DATABASE ${quoteIdent(uniqueDbName)};`);
  } finally {
    await adminClient.end();
  }

  // Construct ephemeral DATABASE_URL and export to process for tests and migrations
  const ephemeralUrl = new URL(url.toString());
  ephemeralUrl.pathname = `/${uniqueDbName}`;
  process.env.DATABASE_URL = ephemeralUrl.toString();

  // Run drizzle migrations against the ephemeral DB.
  // We use drizzle-kit CLI; working directory: server.
  const cwd = path.resolve(__dirname, "..");
  await runCommand("pnpm", ["exec", "drizzle-kit", "migrate"], {
    cwd,
    env: { ...process.env, DATABASE_URL: ephemeralUrl.toString() },
  });

  // Return a teardown that drops the ephemeral DB at the end of the test run
  return async () => {
    const dropClient = new Client({ connectionString: adminUrl.toString() });
    await dropClient.connect();
    try {
      // Terminate any connections and drop database
      await dropClient.query(
        `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1;`,
        [uniqueDbName]
      );
      await dropClient.query(`DROP DATABASE IF EXISTS ${quoteIdent(uniqueDbName)};`);
    } finally {
      await dropClient.end();
    }
  };
}

function quoteIdent(identifier: string) {
  return '"' + identifier.replaceAll('"', '""') + '"';
}

function runCommand(command: string, args: string[], opts: { cwd: string; env: NodeJS.ProcessEnv }) {
  return new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: opts.cwd,
      env: opts.env,
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`${command} ${args.join(" ")} exited with code ${code}`));
      }
    });
    child.on("error", reject);
  });
}


