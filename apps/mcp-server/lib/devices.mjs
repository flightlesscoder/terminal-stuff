// Device-sighting history, shared by the "net" plugin and any locally-added router/gateway
// plugins (any of them can feed observations into the same store). File-backed at
// local/mcp-devices.json (git-ignored) -- this repo has no app store of its own, so a plain
// JSON file plays that role, same as lib/creds.mjs's credential file.
import { readFile, writeFile, mkdir } from "node:fs/promises";

const DEVICES_FILE = new URL("../../../local/mcp-devices.json", import.meta.url);
const HISTORY_DAYS = 60;
const PRESENT_WINDOW_MS = 10 * 60_000;

function normaliseMac(mac) { return mac.trim().toLowerCase().replace(/-/g, ":"); }
function isUsableMac(mac) { return /^([0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(mac) && mac !== "00:00:00:00:00:00"; }

async function loadDevices() {
  try { return JSON.parse(await readFile(DEVICES_FILE, "utf8")); } catch { return {}; }
}
async function saveDevices(devices) {
  await mkdir(new URL(".", DEVICES_FILE), { recursive: true });
  await writeFile(DEVICES_FILE, JSON.stringify(devices, null, 2));
}

export async function recordObservations(observations) {
  const devices = await loadDevices();
  const now = Date.now();
  const today = new Date(now).toISOString().slice(0, 10);
  const cutoffDay = new Date(now - HISTORY_DAYS * 86_400_000).toISOString().slice(0, 10);
  let recorded = 0;
  for (const obs of observations) {
    const mac = normaliseMac(obs.mac);
    if (!isUsableMac(mac)) continue;
    recorded++;
    const existing = devices[mac];
    if (!existing) {
      devices[mac] = {
        mac, ip: obs.ip ?? null, knownIps: obs.ip ? [obs.ip] : [],
        hostname: obs.hostname ?? null, knownHostnames: obs.hostname ? [obs.hostname] : [],
        sources: [obs.source], firstSeen: now, lastSeen: now, seenDays: [today], sightings: 1,
      };
      continue;
    }
    existing.ip = obs.ip ?? existing.ip;
    if (obs.ip && !existing.knownIps.includes(obs.ip)) existing.knownIps = [obs.ip, ...existing.knownIps].slice(0, 12);
    existing.hostname = obs.hostname ?? existing.hostname;
    if (obs.hostname && !existing.knownHostnames.includes(obs.hostname)) existing.knownHostnames = [obs.hostname, ...existing.knownHostnames].slice(0, 12);
    if (!existing.sources.includes(obs.source)) existing.sources.push(obs.source);
    existing.lastSeen = now;
    existing.sightings++;
    if (!existing.seenDays.includes(today)) existing.seenDays.push(today);
    existing.seenDays = existing.seenDays.filter((d) => d >= cutoffDay).sort();
  }
  await saveDevices(devices);
  return recorded;
}

function humanAge(ms) {
  const s = Math.round(ms / 1000);
  if (s < 90) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 90) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export async function summariseDevices({ presentOnly = false } = {}) {
  const devices = await loadDevices();
  const now = Date.now();
  let views = Object.values(devices).map((d) => {
    const daysKnown = Math.max(1, Math.ceil((now - d.firstSeen) / 86_400_000));
    const daysSeen = d.seenDays.length;
    return {
      ...d, daysSeen,
      familiarity: Math.min(1, Number((daysSeen / Math.min(daysKnown, HISTORY_DAYS)).toFixed(2))),
      lastSeenAgo: humanAge(now - d.lastSeen),
      presentNow: now - d.lastSeen < PRESENT_WINDOW_MS,
    };
  }).sort((a, b) => b.lastSeen - a.lastSeen);
  if (presentOnly) views = views.filter((d) => d.presentNow);
  return { devices: views, file: DEVICES_FILE.pathname };
}

export async function scanArp() {
  const { run } = await import("./exec.mjs");
  const res = await run("ip", ["-4", "neigh", "show"], { timeoutMs: 8000 });
  const out = [];
  for (const line of res.stdout.split("\n")) {
    const m = line.match(/^(\S+)\s+dev\s+\S+\s+lladdr\s+(\S+)\s+(\S+)/);
    if (!m) continue;
    if (m[3] === "FAILED" || m[3] === "INCOMPLETE") continue;
    out.push({ ip: m[1], mac: m[2], source: "arp" });
  }
  return out;
}
