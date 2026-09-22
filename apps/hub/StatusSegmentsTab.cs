using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Text.Json.Nodes;
using Terminal.Gui.App;
using Terminal.Gui.Drawing;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace Hub;

/// <summary>Configure, reorder and toggle tmux2k's status bar segments. Segments move between
/// three lists (Left / Right / Off); Up/Down reorder within whichever list is focused. Save
/// writes tmux.statusLeft/statusRight into ~/.config/terminal-stuff/config.jsonc (as {"$replace":
/// [...]}, since order+membership together are the point -- see config/README.md) and, if running
/// inside tmux, applies it live via `tmux set-option` so you see the result immediately.</summary>
internal static class StatusSegmentsTab
{
    // Falls back to this if ~/.tmux/plugins/tmux2k isn't installed yet; keep in sync with that
    // plugin's plugins/*.sh (see setup/tui/modules/tmux.py's PLUGIN_DIRS comment for where it's installed).
    static readonly string[] FallbackSegments =
    [
        "bandwidth", "battery", "cpu", "cpu-temp", "custom", "cwd", "docker", "github", "git", "gpu",
        "group", "keyboard-layout", "mise", "network", "ping", "pomodoro", "ram", "session", "storage",
        "tdo", "time", "updates", "uptime", "volume", "weather",
    ];

    public static View Create(string repoRoot, string home)
    {
        var view = new View { Title = "Status Segments", CanFocus = true, Width = Dim.Fill(), Height = Dim.Fill() };
        var status = new Label { X = 1, Y = Pos.AnchorEnd(1), Width = Dim.Fill(1), Text = "" };
        var selection = new Label { X = 1, Y = Pos.AnchorEnd(2), Width = Dim.Fill(1), Text = "selected: (none)" };

        var allSegments = DiscoverAllSegments(home);
        var left = new ObservableCollection<string>();
        var right = new ObservableCollection<string>();
        var available = new ObservableCollection<string>();

        void LoadFromConfig()
        {
            Jsonc.ResolvedConfig cfg;
            try { cfg = Jsonc.Resolve(repoRoot, Directory.GetCurrentDirectory(), home); }
            catch (Jsonc.JsoncException e) { status.Text = $"config error: {e.Message}"; return; }
            left.Clear(); foreach (var s in cfg.StatusLeft) left.Add(s);
            right.Clear(); foreach (var s in cfg.StatusRight) right.Add(s);
            available.Clear();
            foreach (var s in allSegments)
                if (!left.Contains(s) && !right.Contains(s)) available.Add(s);
            status.Text = "loaded from config";
        }

        var leftPane = MakeList("Left", out var leftList);
        var rightPane = MakeList("Right", out var rightList);
        var availPane = MakeList("Available (off)", out var availList);
        leftList.SetSource(left);
        rightList.SetSource(right);
        availList.SetSource(available);

        leftPane.X = 0; leftPane.Y = 0; leftPane.Width = Dim.Percent(34); leftPane.Height = Dim.Fill(4);
        rightPane.X = Pos.Right(leftPane); rightPane.Y = 0; rightPane.Width = Dim.Percent(34); rightPane.Height = Dim.Fill(4);
        availPane.X = Pos.Right(rightPane); availPane.Y = 0; availPane.Width = Dim.Fill(); availPane.Height = Dim.Fill(4);

        // Which item a button acts on: captured (list + index) at the moment the user last
        // interacted with a list, NOT re-read from lv.SelectedItem at button-click time -- by then
        // focus has moved to the button itself, and ListView.SelectedItem/Value reads back null
        // once the list no longer has focus, so a late read always missed. ValueChanged covers
        // keyboard/mouse navigation to a new row; the MouseEvent fallback also covers a click that
        // lands on the row that was already selected (no "change" to fire ValueChanged for).
        (ObservableCollection<string> Data, ListView View, int Index)? active = null;
        void Track(string label, ObservableCollection<string> data, ListView lv)
        {
            void Capture(int? idx)
            {
                if (idx is not int i || i < 0 || i >= data.Count) return;
                active = (data, lv, i);
                selection.Text = $"selected: {label}[{i}] = {data[i]}";
            }
            lv.ValueChanged += (_, e) => Capture(e.NewValue);
            lv.MouseEvent += (_, __) => Capture(lv.SelectedItem);
        }
        Track("Left", left, leftList);
        Track("Right", right, rightList);
        Track("Available", available, availList);

        void MoveTo(ObservableCollection<string> dest)
        {
            if (active is not var (src, lv, idx) || idx >= src.Count) { status.Text = "select an item first"; return; }
            if (dest == src) return;
            var item = src[idx];
            src.RemoveAt(idx);
            dest.Add(item);
            active = null;
            status.Text = $"moved '{item}'";
        }

        void Reorder(int delta)
        {
            if (active is not var (src, lv, idx) || idx >= src.Count) { status.Text = "select an item first"; return; }
            if (lv == availList) { status.Text = "select a Left/Right item to reorder"; return; }
            int dst = idx + delta;
            if (dst < 0 || dst >= src.Count) return;
            (src[idx], src[dst]) = (src[dst], src[idx]);
            lv.SetSelection(dst, false);
            active = (src, lv, dst);
            status.Text = "reordered";
        }

        var toLeftBtn = new Button { Text = "< Left", X = 0, Y = Pos.Bottom(leftPane) };
        var toRightBtn = new Button { Text = "Right >", X = Pos.Right(toLeftBtn) + 1, Y = Pos.Top(toLeftBtn) };
        var offBtn = new Button { Text = "Off", X = Pos.Right(toRightBtn) + 1, Y = Pos.Top(toLeftBtn) };
        var upBtn = new Button { Text = "Up", X = Pos.Right(offBtn) + 2, Y = Pos.Top(toLeftBtn) };
        var downBtn = new Button { Text = "Down", X = Pos.Right(upBtn) + 1, Y = Pos.Top(toLeftBtn) };
        var saveBtn = new Button { Text = "Save", X = Pos.Right(downBtn) + 2, Y = Pos.Top(toLeftBtn), IsDefault = true };
        var revertBtn = new Button { Text = "Revert", X = Pos.Right(saveBtn) + 1, Y = Pos.Top(toLeftBtn) };

        toLeftBtn.Accepting += (_, __) => MoveTo(left);
        toRightBtn.Accepting += (_, __) => MoveTo(right);
        offBtn.Accepting += (_, __) => MoveTo(available);
        upBtn.Accepting += (_, __) => Reorder(-1);
        downBtn.Accepting += (_, __) => Reorder(1);
        revertBtn.Accepting += (_, __) => LoadFromConfig();
        saveBtn.Accepting += (_, __) =>
        {
            try
            {
                status.Text = Save(repoRoot, home, [.. left], [.. right]);
            }
            catch (Exception e)
            {
                status.Text = $"save failed: {e.Message}";
            }
        };

        var hint = new Label
        {
            X = 0, Y = Pos.Bottom(toLeftBtn), Width = Dim.Fill(),
            Text = "select an item, then a button (or Enter/click); Save writes config + applies live if inside tmux",
        };

        LoadFromConfig();
        view.Add(leftPane, rightPane, availPane, toLeftBtn, toRightBtn, offBtn, upBtn, downBtn, saveBtn, revertBtn, hint, selection, status);
        return view;
    }

    static View MakeList(string title, out ListView listView)
    {
        var pane = new View { Title = title, BorderStyle = LineStyle.Single };
        listView = new ListView { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(), CanFocus = true };
        pane.Add(listView);
        return pane;
    }

    static List<string> DiscoverAllSegments(string home)
    {
        var dir = Path.Combine(home, ".tmux", "plugins", "tmux2k", "plugins");
        if (Directory.Exists(dir))
        {
            var found = Directory.GetFiles(dir, "*.sh")
                .Select(Path.GetFileNameWithoutExtension).Where(n => n is not null)
                .Select(n => n!).OrderBy(n => n).ToList();
            if (found.Count > 0) return found;
        }
        return [.. FallbackSegments];
    }

    static string Save(string repoRoot, string home, List<string> left, List<string> right)
    {
        var dir = Path.Combine(home, ".config", "terminal-stuff");
        var path = Path.Combine(dir, Jsonc.ConfigFileName);
        Directory.CreateDirectory(dir);
        if (!File.Exists(path))
        {
            var template = Path.Combine(repoRoot, "config", "user-template.jsonc");
            File.WriteAllText(path, File.Exists(template) ? File.ReadAllText(template) : "{}\n");
        }
        var text = File.ReadAllText(path);
        text = Jsonc.SetReplaceField(text, ["tmux", "statusLeft"], JsonNode.Parse(System.Text.Json.JsonSerializer.Serialize(left))!);
        text = Jsonc.SetReplaceField(text, ["tmux", "statusRight"], JsonNode.Parse(System.Text.Json.JsonSerializer.Serialize(right))!);
        File.WriteAllText(path, text);

        string liveNote = "";
        var tmuxEnv = Environment.GetEnvironmentVariable("TMUX");
        if (!string.IsNullOrEmpty(tmuxEnv))
        {
            try
            {
                RunTmux("set-option", "-g", "@tmux2k-left-plugins", string.Join(' ', left));
                RunTmux("set-option", "-g", "@tmux2k-right-plugins", string.Join(' ', right));
                RunTmux("refresh-client", "-S");
                liveNote = "; applied live";
            }
            catch (Exception e)
            {
                liveNote = $"; saved, but couldn't apply live ({e.Message})";
            }
        }
        return $"saved to {path}{liveNote}";
    }

    static void RunTmux(params string[] args)
    {
        var psi = new ProcessStartInfo("tmux") { RedirectStandardError = true, RedirectStandardOutput = true };
        foreach (var a in args) psi.ArgumentList.Add(a);
        using var proc = Process.Start(psi) ?? throw new InvalidOperationException("couldn't start tmux");
        proc.WaitForExit(5000);
        if (proc.ExitCode != 0)
            throw new InvalidOperationException(proc.StandardError.ReadToEnd().Trim() is { Length: > 0 } e ? e : $"exit {proc.ExitCode}");
    }
}
