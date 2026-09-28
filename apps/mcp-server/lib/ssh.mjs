// Shared ssh argv-building + run helper, used by the generic ssh/scp tools and by any
// local-only plugin targeting a specific known host. Key-based auth only -- BatchMode=yes
// fails fast instead of hanging on a password prompt nothing is attached to answer.
import { run } from "./exec.mjs";

export function assertHost(host) {
  if (typeof host !== "string" || !/^[A-Za-z0-9._:-]+$/.test(host) || host.startsWith("-")) {
    throw new Error(`Not a valid host: ${JSON.stringify(host)}`);
  }
  return host;
}

export function sshArgs({ host, user, port, identityFile }) {
  assertHost(host);
  const args = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new"];
  if (port) args.push("-p", String(port));
  if (identityFile) args.push("-i", identityFile, "-o", "IdentitiesOnly=yes");
  args.push(user ? `${user}@${host}` : host);
  return args;
}

export async function runSsh(target, command, opts = {}) {
  const res = await run("ssh", [...sshArgs(target), command], { timeoutMs: opts.timeoutMs ?? 60_000 });
  return { code: res.exitCode, stdout: res.stdout, stderr: res.stderr };
}

export async function runSshOrThrow(target, command, opts = {}) {
  const res = await runSsh(target, command, opts);
  if (res.code !== 0) throw new Error(res.stderr.trim() || `Command exited ${res.code}`);
  return res.stdout;
}

/** Quote a value for interpolation into a remote shell command string (single-quote, escape embedded quotes). */
export function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}
