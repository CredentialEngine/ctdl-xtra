#!/usr/bin/env node

/**
 * Utility script starting all dev commands for the project
 * while prefixing the output with the service name similar
 * to docker-compose.
 */

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const rootDir = join(__dirname, '..');

// ANSI color codes
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  client: '\x1b[36m', // Cyan
  server: '\x1b[33m', // Yellow
  worker: '\x1b[35m', // Magenta
};

// Color prefixes for each service
const prefixes = {
  client: `${colors.client}${colors.bright}[client]${colors.reset}`,
  server: `${colors.server}${colors.bright}[server]${colors.reset}`,
  worker: `${colors.worker}${colors.bright}[worker]${colors.reset}`,
};

function prefixOutput(prefix, data) {
  const lines = data.toString().split('\n');
  for (const line of lines) {
    if (line.trim()) {
      console.log(`${prefix} ${line}`);
    }
  }
}

let isShuttingDown = false;

function spawnProcess(name, command, args, cwd) {
  const proc = spawn(command, args, {
    cwd,
    stdio: ['inherit', 'pipe', 'pipe'],
    shell: true,
    detached: false,
  });

  proc.stdout.on('data', (data) => {
    prefixOutput(prefixes[name], data);
  });

  proc.stderr.on('data', (data) => {
    prefixOutput(prefixes[name], data);
  });

  proc.on('error', (error) => {
    console.error(`${prefixes[name]} Error: ${error.message}`);
  });

  proc.on('exit', (code, signal) => {
    // Exit codes:
    // 130 = SIGINT (Ctrl+C) - normal shutdown
    // 143 = SIGTERM - normal shutdown
    // null = process terminated by signal (also normal during shutdown)
    const isNormalShutdown = isShuttingDown && 
      (code === 130 || code === 143 || code === null || signal !== null);
    
    if (!isNormalShutdown && code !== 0 && code !== null) {
      console.error(`${prefixes[name]} Process exited unexpectedly with code ${code}${signal ? ` signal: ${signal}` : ''}`);
    }
  });

  return proc;
}

async function main() {
  console.log('Starting development servers...\n');

  const clientProc = spawnProcess('client', 'pnpm', ['dev'], join(rootDir, 'client'));
  const serverProc = spawnProcess('server', 'pnpm', ['dev'], join(rootDir, 'server'));
  const workerProc = spawnProcess('worker', 'pnpm', ['dev:worker'], join(rootDir, 'server'));
  
  const processes = [clientProc, serverProc, workerProc];

  // Handle cleanup on exit
  const cleanup = async () => {
    if (isShuttingDown) {
      return;
    }
    isShuttingDown = true;
    console.log('\nShutting down development servers...');
    
    // Shut down worker first and wait for it to handle shutdown gracefully
    // This prevents SIGINT from propagating to BullMQ child processes before
    // the worker can close them properly
    if (workerProc && !workerProc.killed) {
      workerProc.kill('SIGINT');
      // Wait for worker to exit (it will exit after closing BullMQ workers)
      await new Promise((resolve) => {
        const timeout = setTimeout(() => {
          resolve();
        }, 2000);
        workerProc.once('exit', () => {
          clearTimeout(timeout);
          resolve();
        });
      });
    }
    
    // Now shut down client and server
    if (clientProc && !clientProc.killed) {
      clientProc.kill('SIGINT');
    }
    if (serverProc && !serverProc.killed) {
      serverProc.kill('SIGINT');
    }
    
    // Give remaining processes time to clean up, then force exit
    setTimeout(() => {
      processes.forEach((proc) => {
        if (proc && !proc.killed) {
          proc.kill('SIGTERM');
        }
      });
      process.exit(0);
    }, 2000);
  };

  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);

  // Keep the script running
  process.on('exit', () => {
    processes.forEach((proc) => {
      if (proc && !proc.killed) {
        proc.kill();
      }
    });
  });
}

main();

