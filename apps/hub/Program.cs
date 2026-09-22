using System.Globalization;
using Hub;
using Terminal.Gui.App;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

// `hub --about` prints the build stamp as key: value lines and exits (used by setup/ to check the build).
if (args.Contains("--about"))
{
    Console.WriteLine($"built: {BuildInfo.BuiltUtc}");
    Console.WriteLine($"commit: {BuildInfo.Commit}");
    Console.WriteLine($"dirty: {BuildInfo.Dirty.ToString().ToLowerInvariant()}");
    return 0;
}

var repoRoot = RepoLocator.Find();
var home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);

using IApplication app = Application.Create().Init();
using var window = new Window { Title = "Terminal Stuff Hub", Width = Dim.Fill(), Height = Dim.Fill() };

var tabs = new Tabs { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(1) };
tabs.Add(AboutTab.Create());
tabs.Add(HelpTab.Create());
try
{
    var cfg = Jsonc.Resolve(repoRoot, Directory.GetCurrentDirectory(), home);
    tabs.Add(SettingsTab.Create(cfg));
}
catch (Jsonc.JsoncException e)
{
    tabs.Add(ErrorTab.Create("Settings", e.Message));
}
tabs.Add(StatusSegmentsTab.Create(repoRoot, home));
tabs.Add(SpeechTab.Create(repoRoot, home));
tabs.Add(SetupTab.Create(repoRoot, app));

var hint = new Label
{
    Text = "click a tab (or Tab key) to switch  ·  Esc quits",
    X = 1,
    Y = Pos.AnchorEnd(1),
};

window.Add(tabs, hint);
app.Run(window);
return 0;
