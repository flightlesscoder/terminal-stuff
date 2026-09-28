// Network tools (Phase 0 group 4.1-4.6): ping, sockets, HTTP probe, status overview, ssh/scp, and
// device-sighting history. Idea from an earlier personal MCP tool set's own network-tools module
// (ping/netstat/http-probe/status/ssh/scp/scan-devices/known-devices); reimplemented against plain
// ping/ss/fetch/ssh/scp/ip, no code shared with it. Ported from local/mcp-extraction/
// tools/net-tools.mjs + net-remote.mjs (Phase 1), where every tool here was exercised live against
// this host's real network and real remote hosts.
//
// Deliberately brand/IP-agnostic: any specific gateway hardware you want `status` to check belongs
// in `mcp.pluginOptions.net.gateways` in your own untracked config.jsonc (an array of {name, host}),
// never hardcoded here -- see this tool's own description.
import { run, assertNotFlag } from "../../lib/exec.mjs";
import { sshArgs } from "../../lib/ssh.mjs";
import { recordObservations, summariseDevices, scanArp } from "../../lib/devices.mjs";

export default {
  description: "Ping, sockets, HTTP probing, ssh/scp, and device-sighting history for the local network.",
  tools: [
    {
      name: "ping",
      description: "Ping a host and report packet loss and round-trip times. Use this first when something is unreachable -- it separates 'the host is down' from 'the service on it is down'. Some devices deliberately drop ICMP; a failed ping there doesn't necessarily mean the device is down.",
      groups: ["network"],
      inputSchema: (z) => ({ host: z.string(), count: z.number().int().positive().max(20).optional() }),
      handler: async ({ host, count = 4 }) => {
        assertHost(host);
        const n = Math.max(1, Math.min(20, Math.floor(count)));
        const res = await run("ping", ["-c", String(n), "-W", "2", host], { timeoutMs: (n + 5) * 2000 });
        const lossMatch = res.stdout.match(/(\d+(?:\.\d+)?)% packet loss/);
        const rttMatch = res.stdout.match(/= ([\d.]+)\/([\d.]+)\/([\d.]+)\/([\d.]+)/);
        return {
          host, reachable: res.exitCode === 0,
          packetLossPercent: lossMatch ? Number(lossMatch[1]) : null,
          rttMs: rttMatch ? { min: Number(rttMatch[1]), avg: Number(rttMatch[2]), max: Number(rttMatch[3]) } : null,
          raw: res.stdout.trim(),
        };
      },
    },
    {
      name: "ports",
      description: "List sockets on this machine -- listening ports, established connections, or both. Use it to find which local port a service is actually on, or to confirm a forwarded port has something behind it.",
      groups: ["network"],
      inputSchema: (z) => ({ state: z.enum(["listening", "established", "both"]).optional() }),
      handler: async ({ state = "listening" } = {}) => {
        const flags = ["-tnp"];
        if (state === "listening") flags.push("-l");
        else if (state === "established") flags.push("-t");
        const res = await run("ss", flags, { timeoutMs: 10_000 });
        if (res.exitCode !== 0) throw new Error(`ss failed: ${res.stderr.trim()}`);
        const lines = res.stdout.split("\n").filter(Boolean);
        const header = lines.shift();
        return { state, header, sockets: lines };
      },
    },
    {
      name: "probe",
      description: "Make an HTTP request and return the status, headers and a size-capped body. Use it to check whether a service behind a forwarded port, or on the LAN, actually answers.",
      groups: ["network"],
      inputSchema: (z) => ({
        url: z.string(), method: z.string().optional(), headers: z.record(z.string(), z.string()).optional(),
        body: z.string().optional(), timeoutMs: z.number().int().positive().optional(),
      }),
      handler: async ({ url, method = "GET", headers = {}, body, timeoutMs = 10_000 }) => {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeoutMs);
        try {
          const started = Date.now();
          const res = await fetch(url, { method, headers, body, signal: ctrl.signal, redirect: "manual" });
          const text = await res.text();
          const capped = text.length > 8192 ? text.slice(0, 8192) + "\n[...truncated...]" : text;
          return { url, status: res.status, ok: res.ok, durationMs: Date.now() - started, headers: Object.fromEntries(res.headers.entries()), body: capped };
        } catch (err) {
          return { url, error: err instanceof Error ? err.message : String(err) };
        } finally {
          clearTimeout(timer);
        }
      },
    },
    {
      name: "status",
      description: "One-shot network overview: default gateway, this host's addresses, and whether any gateways listed in mcp.pluginOptions.net.gateways (your own untracked config -- an array of {name, host}) answer a ping. Call this first before host-specific tools.",
      groups: ["network"],
      handler: async (_args, ctx) => {
        const [route, addr] = await Promise.all([
          run("ip", ["route"], { timeoutMs: 5000 }),
          run("ip", ["-4", "-br", "addr"], { timeoutMs: 5000 }),
        ]);
        const configured = Array.isArray(ctx?.options?.gateways) ? ctx.options.gateways : [];
        const probe = async (host) => (await run("ping", ["-c", "1", "-W", "1", host], { timeoutMs: 3000 })).exitCode === 0;
        const gateways = await Promise.all(configured.map(async (g) => ({ name: g.name, host: g.host, pingsBack: await probe(g.host) })));
        return {
          defaultRoutes: route.stdout.split("\n").filter((l) => l.startsWith("default")),
          addresses: addr.stdout.trim().split("\n"),
          gateways,
        };
      },
    },
    {
      name: "ssh",
      description: "Run a command on a remote host over SSH and return its output. Key-based auth only -- there's no way to answer a password prompt here, so a host that wants one fails immediately.",
      groups: ["network", "remote-exec"],
      inputSchema: (z) => ({
        host: z.string(), command: z.string(), user: z.string().optional(),
        port: z.number().int().optional(), identityFile: z.string().optional(), timeoutMs: z.number().int().positive().optional(),
      }),
      handler: async ({ host, command, user, port, identityFile, timeoutMs = 60_000 }) => {
        const args = [...sshArgs({ host, user, port, identityFile }), command];
        const res = await run("ssh", args, { timeoutMs });
        return { host, command, exitCode: res.exitCode, stdout: res.stdout, stderr: res.stderr };
      },
    },
    {
      name: "scp",
      description: "Copy a file to or from a remote host over SSH. Paths use scp syntax: a local path, or user@host:/remote/path. Key-based auth only.",
      groups: ["network", "remote-exec"],
      inputSchema: (z) => ({ from: z.string(), to: z.string(), port: z.number().int().optional(), identityFile: z.string().optional(), timeoutMs: z.number().int().positive().optional() }),
      handler: async ({ from, to, port, identityFile, timeoutMs = 60_000 }) => {
        const args = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new"];
        if (port) args.push("-P", String(port));
        if (identityFile) args.push("-i", assertNotFlag(identityFile, "identityFile"), "-o", "IdentitiesOnly=yes");
        args.push(from, to);
        const res = await run("scp", args, { timeoutMs });
        if (res.exitCode !== 0) throw new Error(`scp failed: ${res.stderr.trim()}`);
        return { from, to, copied: true };
      },
    },
    {
      name: "scan_devices",
      description: "Sweep this machine's ARP table and fold the results into the device-sightings history (local/mcp-devices.json). Any locally-added router/gateway device-list tools that call recordObservations() feed this same history.",
      groups: ["network", "devices"],
      handler: async () => {
        const observations = await scanArp();
        const recorded = await recordObservations(observations);
        return { source: "arp", observed: observations.length, recorded };
      },
    },
    {
      name: "known_devices",
      description: "The device-sightings history: what's been seen on this network, when, and how consistently ('familiarity' = fraction of days-since-first-seen on which it showed up; near 1 means a fixture).",
      groups: ["network", "devices"],
      inputSchema: (z) => ({ presentOnly: z.boolean().optional() }),
      handler: async ({ presentOnly = false } = {}) => summariseDevices({ presentOnly }),
    },
  ],
};

function assertHost(host) {
  if (typeof host !== "string" || !/^[A-Za-z0-9._:-]+$/.test(host) || host.startsWith("-")) {
    throw new Error(`Not a valid host: ${JSON.stringify(host)}`);
  }
  return host;
}
