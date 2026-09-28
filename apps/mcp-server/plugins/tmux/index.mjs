// Terminal-session control, backed by the user's real tmux server -- deliberately NOT a
// private_server() like the setup TUI's tests use (setup/tui/modules/tmux.py): these tools exist
// to act on the sessions the user is actually looking at. Ported from local/mcp-extraction/tools/
// tmux-tools.mjs (Phase 1), where every tool here was exercised against an isolated scratch tmux
// server (TMUX_TMPDIR) -- see that file's git history / PHASE0-candidates.md for the test notes.
// Idea taken from an earlier personal MCP tool set's own orchestration tools (session/pane control
// for parallel agent work); reimplemented from scratch against plain tmux, no code shared with it.
import { mkdir, appendFile } from "node:fs/promises";
import { run, requireConfirm } from "../../lib/exec.mjs";

const NAMED_KEYS = ["enter", "tab", "escape", "up", "down", "left", "right", "backspace", "delete",
  "home", "end", "pageup", "pagedown", "space", "ctrl-c", "ctrl-d", "ctrl-z", "ctrl-l"];
const KEY_MAP = { enter: "Enter", tab: "Tab", escape: "Escape", up: "Up", down: "Down", left: "Left",
  right: "Right", backspace: "BSpace", delete: "DC", home: "Home", end: "End", pageup: "PageUp",
  pagedown: "PageDown", space: "Space", "ctrl-c": "C-c", "ctrl-d": "C-d", "ctrl-z": "C-z", "ctrl-l": "C-l" };

async function tmux(args) {
  const res = await run("tmux", args);
  if (res.exitCode !== 0) throw new Error(`tmux ${args.join(" ")} failed: ${res.stderr.trim() || `exit ${res.exitCode}`}`);
  return res.stdout;
}
async function tmuxSoft(args) {
  const res = await run("tmux", args);
  return res.exitCode === 0 ? { ok: true, stdout: res.stdout } : { ok: false, stdout: "", stderr: res.stderr.trim() };
}

export default {
  description: "Control the user's real tmux server: list/create/close sessions, read and drive panes, hand messages between sessions, and per-session status/progress/log markers.",
  tools: [
    {
      name: "session_list",
      description: "List tmux sessions with their windows/panes, current path and active pane id.",
      handler: async () => {
        const r = await tmuxSoft(["list-sessions", "-F", "#{session_name}\t#{session_windows}\t#{session_attached}"]);
        if (!r.ok) return { sessions: [], note: r.stderr || "no tmux server running" };
        const sessions = [];
        for (const line of r.stdout.split("\n").filter(Boolean)) {
          const [name, windows, attached] = line.split("\t");
          const panesRaw = await tmuxSoft(["list-panes", "-t", name, "-a",
            "-F", "#{window_index}.#{pane_index}\t#{pane_id}\t#{pane_current_path}\t#{pane_active}\t#{pane_current_command}"]);
          const panes = panesRaw.ok
            ? panesRaw.stdout.split("\n").filter(Boolean).map((l) => {
                const [index, paneId, path, active, cmd] = l.split("\t");
                return { index, paneId, path, active: active === "1", command: cmd };
              })
            : [];
          sessions.push({ name, windows: Number(windows), attached: attached === "1", panes });
        }
        return { sessions };
      },
    },
    {
      name: "session_create",
      description: "Create a new detached tmux session with its own shell.",
      inputSchema: (z) => ({ name: z.string(), cwd: z.string().optional() }),
      handler: async ({ name, cwd }) => {
        const args = ["new-session", "-d", "-s", name];
        if (cwd) args.push("-c", cwd);
        await tmux(args);
        return { created: name, cwd: cwd ?? null };
      },
    },
    {
      name: "session_close",
      description: "Kill a tmux session and every pane in it. Destructive -- requires confirm: true.",
      groups: ["tmux", "destructive"],
      inputSchema: (z) => ({ name: z.string(), confirm: z.boolean().optional() }),
      handler: async ({ name, confirm }) => {
        requireConfirm(confirm, `kill session '${name}' and everything running in it`);
        await tmux(["kill-session", "-t", name]);
        return { closed: name };
      },
    },
    {
      name: "pane_split",
      description: "Split a pane, creating a second shell beside it. New pane inherits the split-from pane's cwd. `target` accepts a session name, session:window, or a pane id from session_list.",
      inputSchema: (z) => ({ target: z.string(), direction: z.enum(["vertical", "horizontal"]).optional() }),
      handler: async ({ target, direction }) => {
        const args = ["split-window", "-t", target, "-P", "-F", "#{pane_id}"];
        args.push(direction === "horizontal" ? "-h" : "-v");
        return { newPane: (await tmux(args)).trim() };
      },
    },
    {
      name: "pane_read",
      description: "Read the recent scrollback of a pane as plain text (escape sequences stripped by tmux itself).",
      inputSchema: (z) => ({ target: z.string(), lines: z.number().int().positive().max(5000).optional() }),
      handler: async ({ target, lines = 200 }) => ({ target, text: await tmux(["capture-pane", "-p", "-t", target, "-S", String(-lines)]) }),
    },
    {
      name: "pane_send_text",
      description: "Type text into a pane's shell. submit=true presses Enter afterwards; otherwise the text is staged at the prompt for a human to review.",
      inputSchema: (z) => ({ target: z.string(), text: z.string(), submit: z.boolean().optional() }),
      handler: async ({ target, text, submit = false }) => {
        await tmux(["send-keys", "-t", target, "-l", "--", text]);
        if (submit) await tmux(["send-keys", "-t", target, "Enter"]);
        return { target, sent: text, submitted: !!submit };
      },
    },
    {
      name: "pane_send_key",
      description: `Send a single named key to a pane: ${NAMED_KEYS.join(", ")}.`,
      inputSchema: (z) => ({ target: z.string(), key: z.enum(NAMED_KEYS) }),
      handler: async ({ target, key }) => {
        await tmux(["send-keys", "-t", target, KEY_MAP[key]]);
        return { target, key };
      },
    },
    {
      name: "session_message",
      description: "Type a line of text into another session's active pane and press Enter -- the mechanism for one agent to hand work to another.",
      inputSchema: (z) => ({ session: z.string(), text: z.string() }),
      handler: async ({ session, text }) => {
        await tmux(["send-keys", "-t", session, "-l", "--", text]);
        await tmux(["send-keys", "-t", session, "Enter"]);
        return { session, sent: text };
      },
    },
    {
      name: "notify",
      description: "Flag a session as needing attention by showing a message on it (tmux display-message). Best-effort -- there is no persistent 'unread' concept in plain tmux.",
      inputSchema: (z) => ({ target: z.string(), message: z.string() }),
      handler: async ({ target, message }) => {
        await tmux(["display-message", "-t", target, message]);
        return { target, message };
      },
    },
    {
      name: "set_status",
      description: "Set a short labelled status string on a session (e.g. a branch name or test result), stored as the tmux user option @ts-status.",
      inputSchema: (z) => ({ session: z.string(), status: z.string() }),
      handler: async ({ session, status }) => {
        await tmux(["set-option", "-t", session, "@ts-status", status]);
        return { session, status };
      },
    },
    {
      name: "set_progress",
      description: "Show a 0.0-1.0 progress value on a session (tmux user option @ts-progress), with an optional label. Pass value: null to clear it.",
      inputSchema: (z) => ({ session: z.string(), value: z.number().min(0).max(1).nullable(), label: z.string().optional() }),
      handler: async ({ session, value, label }) => {
        if (value === null) {
          await tmux(["set-option", "-t", session, "-u", "@ts-progress"]);
          await tmux(["set-option", "-t", session, "-u", "@ts-progress-label"]);
          return { session, cleared: true };
        }
        await tmux(["set-option", "-t", session, "@ts-progress", String(value)]);
        if (label) await tmux(["set-option", "-t", session, "@ts-progress-label", label]);
        return { session, value, label: label ?? null };
      },
    },
    {
      name: "log",
      description: "Append a timestamped line to a session's activity log (a plain file under the repo's git-ignored logs/, one file per session name) -- a coarser-grained trail than pane_read's raw terminal output.",
      inputSchema: (z) => ({ session: z.string(), line: z.string() }),
      handler: async ({ session, line }, ctx) => {
        const dir = `${ctx.repoRoot}/logs/mcp-tmux-sessions`;
        await mkdir(dir, { recursive: true });
        const file = `${dir}/${encodeURIComponent(session)}.log`;
        await appendFile(file, `${new Date().toISOString()} ${line}\n`);
        return { session, logged: line };
      },
    },
  ],
};
