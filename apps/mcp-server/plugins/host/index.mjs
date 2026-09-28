// Local container + host tools (Phase 0 group 5.1-5.4). Runtime is detected, not assumed -- this
// box has podman, and the same code should work if pointed at a docker host. Idea from an earlier
// personal MCP tool set's own container/system probes; reimplemented from scratch against
// `podman`/`docker`, `nvidia-smi`, /proc. Ported from local/mcp-extraction/tools/container-tools.mjs
// (Phase 1), verified live against this machine's real podman containers and GPU.
import { run, requireConfirm } from "../../lib/exec.mjs";

let cachedRuntime = null;
async function detectRuntime() {
  if (cachedRuntime) return cachedRuntime;
  for (const rt of ["podman", "docker"]) {
    const r = await run("sh", ["-c", `command -v ${rt}`], { timeoutMs: 5000 });
    if (r.exitCode === 0) { cachedRuntime = rt; return rt; }
  }
  return null;
}

function computeCpuBusy(line1, line2) {
  const parse = (l) => l.trim().split(/\s+/).slice(1).map(Number);
  const a = parse(line1), b = parse(line2);
  if (a.length < 4 || b.length < 4) return null;
  const totalA = a.reduce((s, v) => s + v, 0), totalB = b.reduce((s, v) => s + v, 0);
  const totalDelta = totalB - totalA, idleDelta = b[3] - a[3];
  return totalDelta <= 0 ? null : Number((100 * (1 - idleDelta / totalDelta)).toFixed(1));
}

export default {
  description: "This machine's own containers (podman or docker, auto-detected) and host load (CPU/RAM/GPU/disk/uptime).",
  tools: [
    {
      name: "container_list",
      description: "List containers (podman or docker, whichever this host has), with state and status.",
      groups: ["containers"],
      handler: async () => {
        const runtime = await detectRuntime();
        if (!runtime) return { runtime: null, containers: [], note: "no podman or docker on PATH" };
        const res = await run(runtime, ["ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}\t{{.Image}}"], { timeoutMs: 15_000 });
        if (res.exitCode !== 0) throw new Error(`${runtime} ps failed: ${res.stderr.trim()}`);
        const containers = res.stdout.split("\n").filter(Boolean).map((l) => {
          const [name, state, status, image] = l.split("\t");
          return { name, state, status, image };
        });
        return { runtime, containers };
      },
    },
    {
      name: "container_logs",
      description: "Read recent log output from one container (stdout+stderr merged, since many images log to stderr).",
      groups: ["containers"],
      inputSchema: (z) => ({ id: z.string(), tail: z.number().int().positive().max(5000).optional() }),
      handler: async ({ id, tail = 200 }) => {
        const runtime = await detectRuntime();
        if (!runtime) throw new Error("no podman or docker on PATH");
        const res = await run(runtime, ["logs", "--tail", String(Math.max(1, Math.min(5000, tail))), id], { timeoutMs: 15_000 });
        return { runtime, id, log: res.stdout || res.stderr };
      },
    },
    {
      name: "container_action",
      description: "Start, stop, or restart a container. Stopping/restarting is disruptive to whatever depends on it -- requires confirm: true.",
      groups: ["containers", "destructive"],
      inputSchema: (z) => ({ id: z.string(), action: z.enum(["start", "stop", "restart"]), confirm: z.boolean().optional() }),
      handler: async ({ id, action, confirm }) => {
        if (action !== "start") requireConfirm(confirm, `${action} container '${id}', disrupting whatever depends on it`);
        const runtime = await detectRuntime();
        if (!runtime) throw new Error("no podman or docker on PATH");
        const res = await run(runtime, [action, id], { timeoutMs: 45_000 });
        if (res.exitCode !== 0) throw new Error(`${runtime} ${action} ${id} failed: ${res.stderr.trim()}`);
        return { runtime, id, action, ok: true };
      },
    },
    {
      name: "load",
      description: "Point-in-time snapshot of this host's load: CPU busy%, RAM, GPU (if nvidia-smi is present), disk usage, uptime.",
      groups: ["host"],
      handler: async () => {
        const [stat1, memRes, loadRes, diskRes, uptimeRes] = await Promise.all([
          run("sh", ["-c", "grep '^cpu ' /proc/stat"], { timeoutMs: 5000 }),
          run("sh", ["-c", "free -b | sed -n '2p;3p'"], { timeoutMs: 5000 }),
          run("sh", ["-c", "cut -d' ' -f1-3 /proc/loadavg"], { timeoutMs: 5000 }),
          run("df", ["-B1", "--output=source,size,used,target", "-x", "tmpfs", "-x", "devtmpfs", "-x", "efivarfs"], { timeoutMs: 5000 }),
          run("sh", ["-c", "cut -d' ' -f1 /proc/uptime"], { timeoutMs: 5000 }),
        ]);
        await new Promise((r) => setTimeout(r, 400));
        const stat2 = await run("sh", ["-c", "grep '^cpu ' /proc/stat"], { timeoutMs: 5000 });
        const cpuBusyPercent = computeCpuBusy(stat1.stdout, stat2.stdout);
        const gpuRes = await run("nvidia-smi", ["--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"], { timeoutMs: 5000 }).catch(() => null);
        const gpus = gpuRes && gpuRes.exitCode === 0
          ? gpuRes.stdout.split("\n").filter(Boolean).map((l) => {
              const [index, name, memUsed, memTotal, util, temp] = l.split(",").map((s) => s.trim());
              return { index: Number(index), name, memUsedMb: Number(memUsed), memTotalMb: Number(memTotal), utilPercent: Number(util), tempC: Number(temp) };
            })
          : [];
        const [memLine] = memRes.stdout.split("\n");
        const [, memTotal, memUsed] = memLine?.split(/\s+/) ?? [];
        return {
          cpuBusyPercent, load: loadRes.stdout.trim().split(" ").map(Number),
          memTotalBytes: Number(memTotal), memUsedBytes: Number(memUsed), gpus,
          disks: diskRes.stdout.trim().split("\n").slice(1).map((l) => {
            const [source, size, used, target] = l.split(/\s+/);
            return { source, sizeBytes: Number(size), usedBytes: Number(used), target };
          }),
          uptimeSeconds: Number(uptimeRes.stdout.trim()),
        };
      },
    },
  ],
};
