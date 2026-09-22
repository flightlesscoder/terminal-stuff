using System.Collections.ObjectModel;
using System.Text.Json;
using Terminal.Gui.Drawing;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace Hub;

/// <summary>Pick between the kitty themes in themes/kitty/ (each a folder: theme.json + kitty.conf
/// + optional tab_bar.py -- see themes/kitty/README.md). Apply writes the chosen theme's kitty.conf
/// into ~/.kitty.local.conf as a managed block (marker "kitty-theme", BlockFile.cs -- same
/// convention as setup/tui/core.py's Ctx.ensure_block) and, if the theme has one, deploys
/// tab_bar.py to ~/.config/kitty/tab_bar.py (kitty only ever looks for that file in its own config
/// dir, never relative to whatever file included the theme).
///
/// Two independent implementations of "apply a kitty theme" -- this one (interactive switching)
/// and setup/tui/modules/kitty.py's kitty-theme step (non-interactive default for a fresh machine)
/// -- change one, change the other.</summary>
internal static class KittyThemeTab
{
    record ThemeInfo(string Slug, string Name, string Description, string Dir);

    public static View Create(string repoRoot, string home)
    {
        var view = new View { Title = "Kitty Theme", CanFocus = true, Width = Dim.Fill(), Height = Dim.Fill() };
        var status = new Label { X = 1, Y = Pos.AnchorEnd(1), Width = Dim.Fill(1), Text = "" };

        var themes = Discover(Path.Combine(repoRoot, "themes", "kitty"));
        var localConf = Path.Combine(home, ".kitty.local.conf");
        var applied = CurrentSlug(localConf, themes);

        var listPane = new View { Title = "Themes", BorderStyle = LineStyle.Single, X = 0, Y = 0, Width = Dim.Percent(36), Height = Dim.Fill(3) };
        var list = new ListView { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(), CanFocus = true };
        listPane.Add(list);

        var detail = new Label { X = Pos.Right(listPane) + 2, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(3), Text = "" };

        var labels = new ObservableCollection<string>();
        void RefreshLabels()
        {
            labels.Clear();
            foreach (var t in themes) labels.Add((t.Slug == applied ? "* " : "  ") + t.Name);
        }
        RefreshLabels();
        list.SetSource(labels);

        void ShowDetail(int i)
        {
            if (i < 0 || i >= themes.Count) { detail.Text = ""; return; }
            var t = themes[i];
            var tag = t.Slug == applied ? " (currently applied)" : "";
            var extra = File.Exists(Path.Combine(t.Dir, "tab_bar.py")) ? "\n\nUses a custom tab_bar.py (clock/icon, etc.)." : "";
            detail.Text = $"{t.Name}{tag}\n\n{t.Description}{extra}";
        }

        // Same "capture at interaction time" gotcha as StatusSegmentsTab.cs: ListView.SelectedItem
        // reads back null once the list isn't focused, and a Button.Accepting handler always runs
        // after focus has moved to the button -- so track selection via ValueChanged (keyboard/new
        // row) plus a MouseEvent fallback (a click on the row that was already selected).
        int selected = Math.Max(0, themes.FindIndex(t => t.Slug == applied));
        void Capture(int? idx)
        {
            if (idx is not int i || i < 0 || i >= themes.Count) return;
            selected = i;
            ShowDetail(i);
        }
        list.ValueChanged += (_, e) => Capture(e.NewValue);
        list.MouseEvent += (_, __) => Capture(list.SelectedItem);
        if (themes.Count > 0) { list.SetSelection(selected, false); ShowDetail(selected); }

        var applyBtn = new Button { Text = "Apply", X = 0, Y = Pos.Bottom(listPane), IsDefault = true };
        applyBtn.Accepting += (_, __) =>
        {
            if (themes.Count == 0) { status.Text = "no themes found under themes/kitty/"; return; }
            // Snapshot the target index before touching the list: RefreshLabels() clears and
            // re-adds the ObservableCollection, which fires ValueChanged (list.MouseEvent doesn't
            // fire here, but this is the same "don't trust the list's own state after you've
            // changed it" lesson as StatusSegmentsTab.cs's Track()) -- that re-enters Capture()
            // and stomps `selected` back to whatever the reset lands on, so reading `selected`
            // again after RefreshLabels() showed the wrong theme's detail even though Apply()
            // itself (which ran first, using the pre-refresh value) had already applied correctly.
            var i = selected;
            try
            {
                status.Text = Apply(themes[i], localConf, home);
                applied = themes[i].Slug;
                RefreshLabels();
                list.SetSelection(i, false);
                selected = i;
                ShowDetail(i);
            }
            catch (Exception e)
            {
                status.Text = $"apply failed: {e.Message}";
            }
        };

        var hint = new Label
        {
            X = 0, Y = Pos.Bottom(applyBtn), Width = Dim.Fill(),
            Text = "Apply writes ~/.kitty.local.conf (+ tab_bar.py if the theme has one). Reload kitty with ctrl+shift+f5, or restart it.",
        };

        view.Add(listPane, detail, applyBtn, hint, status);
        return view;
    }

    static List<ThemeInfo> Discover(string themesDir)
    {
        var result = new List<ThemeInfo>();
        if (!Directory.Exists(themesDir)) return result;
        foreach (var dir in Directory.GetDirectories(themesDir).OrderBy(d => d, StringComparer.Ordinal))
        {
            var jsonPath = Path.Combine(dir, "theme.json");
            var confPath = Path.Combine(dir, "kitty.conf");
            if (!File.Exists(jsonPath) || !File.Exists(confPath)) continue;
            try
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(jsonPath));
                var root = doc.RootElement;
                var name = root.TryGetProperty("name", out var n) ? n.GetString() ?? Path.GetFileName(dir) : Path.GetFileName(dir);
                var desc = root.TryGetProperty("description", out var d) ? d.GetString() ?? "" : "";
                result.Add(new ThemeInfo(Path.GetFileName(dir), name, desc, dir));
            }
            catch (JsonException)
            {
                // one malformed theme.json shouldn't take the whole picker down; just skip it.
            }
        }
        return result;
    }

    static string? CurrentSlug(string localConf, List<ThemeInfo> themes)
    {
        var body = BlockFile.ReadBlock(localConf, "kitty-theme");
        if (body is null) return null;
        foreach (var t in themes)
        {
            var confPath = Path.Combine(t.Dir, "kitty.conf");
            if (File.Exists(confPath) && File.ReadAllText(confPath).Trim('\n', '\r') == body)
                return t.Slug;
        }
        return null;
    }

    static string Apply(ThemeInfo theme, string localConf, string home)
    {
        var body = File.ReadAllText(Path.Combine(theme.Dir, "kitty.conf"));
        var changed = BlockFile.EnsureBlock(localConf, "kitty-theme", body);
        var tabBarSrc = Path.Combine(theme.Dir, "tab_bar.py");
        if (File.Exists(tabBarSrc))
        {
            var tabBarDest = Path.Combine(home, ".config", "kitty", "tab_bar.py");
            Directory.CreateDirectory(Path.GetDirectoryName(tabBarDest)!);
            File.Copy(tabBarSrc, tabBarDest, overwrite: true);
        }
        return changed ? $"applied '{theme.Slug}'" : $"'{theme.Slug}' already applied";
    }
}
