using System.Collections.ObjectModel;
using Terminal.Gui.App;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace Hub;

/// <summary>Settings tab: a list of sections on the left, that section's content on the right.
/// Add a section by adding one entry to Sections in Create() -- each just builds its own View.</summary>
internal static class SettingsTab
{
    public static View Create(Jsonc.ResolvedConfig cfg)
    {
        var view = new View { Title = "Settings", CanFocus = true, Width = Dim.Fill(), Height = Dim.Fill() };

        (string Name, Func<View> Build)[] sections =
        [
            ("Paths", () => BuildPaths(cfg)),
            // More settings sections go here as they're added.
        ];

        var sectionNames = new ObservableCollection<string>(sections.Select(s => s.Name));
        var list = new View { Title = "Section", X = 0, Y = 0, Width = 20, Height = Dim.Fill(), BorderStyle = Terminal.Gui.Drawing.LineStyle.Single };
        var sectionList = new ListView { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill() };
        sectionList.SetSource(sectionNames);
        list.Add(sectionList);

        var content = new View { X = Pos.Right(list), Y = 0, Width = Dim.Fill(), Height = Dim.Fill() };

        void ShowSection(int index)
        {
            content.RemoveAll();
            if (index < 0 || index >= sections.Length) return;
            var built = sections[index].Build();
            built.X = 0; built.Y = 0; built.Width = Dim.Fill(); built.Height = Dim.Fill();
            content.Add(built);
            content.SetNeedsDraw();
        }

        sectionList.ValueChanged += (_, e) => ShowSection(e.NewValue ?? -1);
        sectionList.SetSelection(0, false);
        ShowSection(0);

        view.Add(list, content);
        return view;
    }

    static View BuildPaths(Jsonc.ResolvedConfig cfg)
    {
        var pane = new View { Title = "Paths", BorderStyle = Terminal.Gui.Drawing.LineStyle.Single };
        var hint = new Label
        {
            Text = "Important paths for this setup. Add your own from ~/.config/terminal-stuff/config.jsonc (see config/README.md).",
            X = 1, Y = 0, Width = Dim.Fill(1),
        };
        var rows = new ObservableCollection<string>(cfg.Paths.Select(FormatRow));
        var list = new ListView { X = 1, Y = 2, Width = Dim.Fill(1), Height = Dim.Fill(1) };
        list.SetSource(rows);
        pane.Add(hint, list);
        return pane;
    }

    static string FormatRow(Jsonc.PathEntry p)
    {
        bool exists = Directory.Exists(p.Path) || File.Exists(p.Path);
        string mark = exists ? "✔" : "✘";
        return $"{mark} {p.Name,-16} {p.Path}";
    }
}
