// Subprocess runner shared by every tool here.
//
// Every caller passes an argv array, never a shell string -- a hostname, path or
// container id that arrives from a model is an argument, not something a shell
// gets to interpret. Do not add a `shell: true` convenience; this is a clean-room
// reimplementation of an idea from an earlier personal MCP tool set (argv-only
// exec, output capped, ENOENT reported as "not installed" rather than a crash)
// -- no code or text copied from it.

import { spawn } from "node:child_process";

const MAX_OUTPUT_BYTES = 96 * 1024;

function cap(buf) {
  if (Buffer.byteLength(buf, "utf8") <= MAX_OUTPUT_BYTES) return { text: buf, truncated: false };
  const sliced = Buffer.from(buf, "utf8").subarray(-MAX_OUTPUT_BYTES).toString("utf8");
  return { text: `[... output truncated ...]\n${sliced}`, truncated: true };
}

/**
 * Run `command` with argv `args`. Resolves even on nonzero exit (that's a
 * legitimate answer, not a JS exception) -- only a missing binary or a spawn
 * failure rejects.
 */
export function run(command, args, opts = {}) {
  const timeoutMs = opts.timeoutMs ?? 20_000;
  const started = Date.now();
  return new Promise((resolve, reject) => {
    let child;
    try {
      child = spawn(command, args, {
        cwd: opts.cwd,
        env: { ...process.env, ...(opts.env ?? {}) },
        stdio: ["pipe", "pipe", "pipe"],
      });
    } catch (err) {
      reject(err);
      return;
    }
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let settled = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("error", (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      reject(new Error(`Could not run '${command}': ${err.message}. Is it installed and on PATH?`));
    });
    child.on("close", (code, signal) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const out = cap(stdout);
      const errOut = cap(stderr);
      resolve({
        command,
        args,
        exitCode: code,
        signal,
        stdout: out.text,
        stderr: errOut.text,
        durationMs: Date.now() - started,
        timedOut,
        truncated: out.truncated || errOut.truncated,
      });
    });
    if (opts.stdin !== undefined) child.stdin.end(opts.stdin);
    else child.stdin.end();
  });
}

/** Argument guard (not an injection guard -- there is no shell): rejects a
 * value that looks like a flag rather than a host/path, e.g. "-oProxyCommand=...". */
export function assertNotFlag(value, label) {
  if (typeof value !== "string" || value.startsWith("-")) {
    throw new Error(`${label} must not look like a flag: ${JSON.stringify(value)}`);
  }
  return value;
}

export function requireConfirm(confirm, consequence) {
  if (!confirm) {
    throw new Error(`Refused without confirm: true. This would ${consequence}.`);
  }
}
