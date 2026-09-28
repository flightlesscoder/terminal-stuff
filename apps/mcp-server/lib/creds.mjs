// Credential loading for network/router/remote-host tools: environment variable
// first, then an optional git-ignored local file (never this repo's tracked
// config, and never anything under version control). Mirrors the shape of an
// earlier personal MCP tool set's own credential loader (env wins over stored
// value, describe-without-disclosing), reimplemented against a plain JSON file
// instead of its app store, since these scripts have no app/db of their own.
//
// File location: local/mcp-creds.json (git-ignored via local/*, listed
// nowhere else). Never printed in full by any tool -- only
// describeCredentials()'s boolean "is it set" view is. Shared by both these
// tracked MCP plugins and the standalone Phase-1 tools under
// local/mcp-extraction/tools/ (its own lib/creds.mjs points at the same file),
// so there's exactly one place credentials live regardless of which surface
// you're testing from.
import { readFile } from "node:fs/promises";

const CREDS_FILE = new URL("../../../local/mcp-creds.json", import.meta.url);

let cache = null;
async function loadFile() {
  if (cache) return cache;
  try {
    cache = JSON.parse(await readFile(CREDS_FILE, "utf8"));
  } catch {
    cache = {};
  }
  return cache;
}

export async function getCredential(envVar, fileKey) {
  if (process.env[envVar]) return { value: process.env[envVar], source: "env" };
  const file = await loadFile();
  if (file[fileKey]) return { value: file[fileKey], source: "file" };
  return { value: undefined, source: "unset" };
}

export function requireCredential(value, label, howToSet) {
  if (!value) {
    throw new Error(`${label} is not set. ${howToSet}`);
  }
  return value;
}

export async function describeCredentials(keys) {
  const out = {};
  for (const [name, [envVar, fileKey]] of Object.entries(keys)) {
    const { source } = await getCredential(envVar, fileKey);
    out[name] = { set: source !== "unset", source };
  }
  return out;
}

export const CREDS_FILE_PATH = CREDS_FILE.pathname;
