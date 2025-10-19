#!/usr/bin/env node
/*
  Orchestrates dev processes:
  - server: npm run dev (in server)
  - worker: npm run dev:worker (in server)
  - client: npm run dev (in client)
  Prefixes logs with labels and handles graceful shutdown.
*/

const { spawn } = require('child_process');
const path = require('path');

const ANSI = {
  reset: '\x1b[0m',
  colors: {
    server: '\x1b[36m', // cyan
    worker: '\x1b[35m', // magenta
    client: '\x1b[32m', // green
  },
};

function coloredPrefix(label) {
  const color = ANSI.colors[label] || '';
  if (!color) return `${label}: `;
  return `${color}${label}:${ANSI.reset} `;
}

/**
 * Spawn a child process with prefixed, line-buffered stdout/stderr.
 * Returns the child and a promise that resolves with its exit code when it exits.
 */
function spawnWithPrefix(label, command, args, options) {
  const child = spawn(command, args, {
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: process.platform === 'win32',
    ...options,
  });

  const prefix = coloredPrefix(label);

  function pipe(stream, write) {
    let buffer = '';
    stream.on('data', (chunk) => {
      buffer += chunk.toString();
      let idx;
      while ((idx = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        write(prefix + line + '\n');
      }
    });
    stream.on('end', () => {
      if (buffer.length > 0) {
        write(prefix + buffer + '\n');
        buffer = '';
      }
    });
  }

  pipe(child.stdout, (data) => process.stdout.write(data));
  pipe(child.stderr, (data) => process.stderr.write(data));

  const exitPromise = new Promise((resolve) => {
    child.on('exit', (code, signal) => {
      const reason = signal ? `signal ${signal}` : `code ${code}`;
      process.stdout.write(`${prefix}process exited with ${reason}\n`);
      resolve({ code, signal });
    });
  });

  return { child, exitPromise };
}

function main() {
  const repoRoot = path.resolve(__dirname, '..');
  const serverCwd = path.join(repoRoot, 'server');
  const clientCwd = path.join(repoRoot, 'client');

  const children = [];

  // server dev
  const serverDev = spawnWithPrefix('server', 'npm', ['run', 'dev'], { cwd: serverCwd, env: process.env });
  children.push(serverDev.child);

  // server worker
  const workerDev = spawnWithPrefix('worker', 'npm', ['run', 'dev:worker'], { cwd: serverCwd, env: process.env });
  children.push(workerDev.child);

  // client dev
  const clientDev = spawnWithPrefix('client', 'npm', ['run', 'dev'], { cwd: clientCwd, env: process.env });
  children.push(clientDev.child);

  // If any child exits with non-zero, exit this orchestrator with that code.
  // If a child exits with zero (e.g., intentional), we keep running unless all are done.
  let exiting = false;
  function handleChildExit(result) {
    if (exiting) return;
    if (result.signal) {
      initiateShutdown();
      return;
    }
    if (typeof result.code === 'number' && result.code !== 0) {
      process.stderr.write(`orchestrator: child exited with code ${result.code}, shutting down...\n`);
      initiateShutdown(result.code);
    }
  }

  Promise.race([serverDev.exitPromise, workerDev.exitPromise, clientDev.exitPromise]).then(handleChildExit);

  function initiateShutdown(exitCode = 0) {
    if (exiting) return;
    exiting = true;
    process.stdout.write('orchestrator: initiating shutdown...\n');
    // Send SIGINT first, then SIGTERM, then SIGKILL fallback
    const signals = ['SIGINT', 'SIGTERM'];
    const killAll = (signal) => {
      for (const c of children) {
        try {
          if (!c.killed) c.kill(signal);
        } catch {}
      }
    };

    killAll('SIGINT');
    setTimeout(() => killAll('SIGTERM'), 2000);
    setTimeout(() => {
      for (const c of children) {
        try {
          if (!c.killed) c.kill('SIGKILL');
        } catch {}
      }
      process.exit(exitCode);
    }, 4000);
  }

  process.on('SIGINT', () => initiateShutdown(0));
  process.on('SIGTERM', () => initiateShutdown(0));
  process.on('exit', () => {
    // best-effort cleanup if not already done
    for (const c of children) {
      try {
        if (!c.killed) c.kill('SIGTERM');
      } catch {}
    }
  });
}

main();


