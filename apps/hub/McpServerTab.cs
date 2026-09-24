using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Terminal.Gui.Drawing;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace Hub;

/// <summary>Control apps/mcp-server: see every discoverable plugin (built-in ones in
/// apps/mcp-server/plugins/, private ones in local/mcp-plugins/), toggle which load, and check that
/// pi is wired to the server. Save writes mcp.enabledPlugins into ~/.config/terminal-stuff/
/// config.jsonc as {"$replace": [...]} (same as StatusSegmentsTab -- see config/README.md). The
/// server reads that config when pi starts it, so restart pi (or `/mcp reconnect terminal-stuff`).
/// The plugin list comes from `node server.mjs --list-plugins`, so this never duplicates the
/// server's own discovery rules.</summary>
internal static class McpServerTab
{
    record ToolInfo(string Name, string Description);
    record PluginInfo(string Name, string Source, string Description, string? Error, List<ToolInfo> Tools);

    public static View Create(string repoRoot, string home)
    {
        var serverDir = Path.Combine(repoRoot, "apps", "mcp-server");
        if (!Directory.Exists(Path.Combine(serverDir, "node_modules")))
            return ErrorTab.Create("MCP Server", "MCP server dependencies aren't installed. Run ./setup/setup.sh -> ai-agents module -> 'mcp-server-install'.");

        var (plugins, enabledNow) = Discover(serverDir);
        var enabled = new HashSet<string>(enabledNow);

        var view = new View { Title = "MCP Server", CanFocus = true, Width = Dim.Fill(), Height = Dim.Fill() };
        var status = new Label { X = 1, Y = Pos.AnchorEnd(1), Width = Dim.Fill(1), Text = "" };

        var listPane = new View { Title = "Plugins", BorderStyle = LineStyle.Single, X = 0, Y = 0, Width = Dim.Percent(36), Height = Dim.Fill(5) };
        var list = new ListView { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(), CanFocus = true };
        listPane.Add(list);
        var detail = new Label { X = Pos.Right(listPane) + 2, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(4), Text = "", HotKeySpecifier = new System.Text.Rune(0xFFFF) };   // tool names contain "_"

        var labels = new ObservableCollection<string>();
        void RefreshLabels()
        {
            labels.Clear();
            foreach (var p in plugins) labels.Add($"[{(enabled.Contains(p.Name) ? "x" : " ")}] {p.Name}{(p.Source == "local" ? " (local)" : "")}");
        }
        RefreshLabels();
        list.SetSource(labels);

        void ShowDetail(int i)
        {
            if (i < 0 || i >= plugins.Count) { detail.Text = "No plugins found."; return; }
            var p = plugins[i];
            var sb = new StringBuilder();
            sb.AppendLine($"{p.Name}  [{p.Source}]  {(enabled.Contains(p.Name) ? "ENABLED" : "disabled")}");
            sb.AppendLine().AppendLine(p.Description);
            if (p.Error is not null) sb.AppendLine().AppendLine($"LOAD ERROR: {p.Error}");
            sb.AppendLine().AppendLine($"Tools ({p.Tools.Count}):");
            foreach (var t in p.Tools) sb.AppendLine($"  {t.Name}");
            detail.Text = sb.ToString();
        }

        // Selection tracking: same "capture at interaction time, snapshot before refreshing the
        // list" rules as KittyThemeTab.cs / StatusSegmentsTab.cs (see CLAUDE.md).
        int selected = 0;
        void Capture(int? idx)
        {
            if (idx is not int i || i < 0 || i >= plugins.Count) return;
            selected = i;
            ShowDetail(i);
        }
        list.ValueChanged += (_, e) => Capture(e.NewValue);
        list.MouseEvent += (_, __) => Capture(list.SelectedItem);
        if (plugins.Count > 0) { list.SetSelection(0, false); ShowDetail(0); } else ShowDetail(-1);

        var toggleBtn = new Button { Text = "Toggle", X = 0, Y = Pos.Bottom(listPane) };
        toggleBtn.Accepting += (_, __) =>
        {
            if (plugins.Count == 0) return;
            var i = selected;
            var name = plugins[i].Name;
            if (!enabled.Remove(name)) enabled.Add(name);
            RefreshLabels();
            list.SetSelection(i, false);
            selected = i;
            ShowDetail(i);
            status.Text = "unsaved change -- press Save";
        };
        var saveBtn = new Button { Text = "Save", X = Pos.Right(toggleBtn) + 2, Y = Pos.Bottom(listPane), IsDefault = true };
        saveBtn.Accepting += (_, __) =>
        {
            try { status.Text = Save(repoRoot, home, plugins.Select(p => p.Name).Where(enabled.Contains).ToList()); }
            catch (Exception e) { status.Text = $"save failed: {e.Message}"; }
        };

        var hint = new Label
        {
            X = 0, Y = Pos.Bottom(toggleBtn), Width = Dim.Fill(),
            Text = "Private plugins: local/mcp-plugins/<name>/index.mjs. Restart pi after saving.\n" + PiWiring(home, serverDir),
        };

        view.Add(listPane, detail, toggleBtn, saveBtn, hint, status);
        return view;
    }

    static (List<PluginInfo>, List<string>) Discover(string serverDir)
    {
        var psi = new ProcessStartInfo("node") { RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = serverDir };
        psi.ArgumentList.Add("server.mjs");
        psi.ArgumentList.Add("--list-plugins");
        using var proc = Process.Start(psi) ?? throw new InvalidOperationException("couldn't start node");
        var stdout = proc.StandardOutput.ReadToEnd();
        proc.WaitForExit(15000);
        if (proc.ExitCode != 0) throw new InvalidOperationException($"server.mjs --list-plugins failed: {proc.StandardError.ReadToEnd().Trim()}");
        var plugins = new List<PluginInfo>();
        var on = new List<string>();
        using var doc = JsonDocument.Parse(stdout);
        foreach (var p in doc.RootElement.EnumerateArray())
        {
            var name = p.GetProperty("name").GetString() ?? "";
            if (p.GetProperty("enabled").GetBoolean()) on.Add(name);
            var tools = p.GetProperty("tools").EnumerateArray()
                .Select(t => new ToolInfo(t.GetProperty("name").GetString() ?? "", t.TryGetProperty("description", out var d) ? d.GetString() ?? "" : "")).ToList();
            plugins.Add(new PluginInfo(name, p.GetProperty("source").GetString() ?? "",
                p.TryGetProperty("description", out var desc) ? desc.GetString() ?? "" : "",
                p.TryGetProperty("error", out var err) ? err.GetString() : null, tools));
        }
        return (plugins, on);
    }

    /// <summary>One line: is pi's MCP config pointing at this repo's server? (Read-only; the
    /// ai-agents setup module's 'mcp-pi-wire' step is what writes it.)</summary>
    static string PiWiring(string home, string serverDir)
    {
        var agentDir = Environment.GetEnvironmentVariable("PI_CODING_AGENT_DIR") is { Length: > 0 } d ? d : Path.Combine(home, ".pi", "agent");
        var path = Path.Combine(agentDir, "mcp.json");
        try
        {
            if (!File.Exists(path)) return $"pi: not wired ({path} missing) -- setup.sh -> ai-agents -> 'mcp-pi-wire'";
            var entry = JsonNode.Parse(File.ReadAllText(path))?["mcpServers"]?["terminal-stuff"];
            if (entry is null) return "pi: not wired (no 'terminal-stuff' entry) -- setup.sh -> ai-agents -> 'mcp-pi-wire'";
            var want = Path.Combine(serverDir, "server.mjs");
            return entry["args"]?[0]?.GetValue<string>() == want ? $"pi: wired ({path})" : $"pi: entry points elsewhere ({entry["args"]?[0]}) -- re-run 'mcp-pi-wire'";
        }
        catch (Exception e) { return $"pi: couldn't read {path} ({e.Message})"; }
    }

    static string Save(string repoRoot, string home, List<string> names)
    {
        var dir = Path.Combine(home, ".config", "terminal-stuff");
        var path = Path.Combine(dir, Jsonc.ConfigFileName);
        Directory.CreateDirectory(dir);
        if (!File.Exists(path))
        {
            var template = Path.Combine(repoRoot, "config", "user-template.jsonc");
            File.WriteAllText(path, File.Exists(template) ? File.ReadAllText(template) : "{}\n");
        }
        var text = Jsonc.SetReplaceField(File.ReadAllText(path), ["mcp", "enabledPlugins"], JsonNode.Parse(JsonSerializer.Serialize(names))!);
        File.WriteAllText(path, text);
        return $"saved {names.Count} enabled plugin(s) to {path}; restart pi to pick it up";
    }
}
