using System.Globalization;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace Hub;

/// <summary>First tab: when this binary was built and from which commit.</summary>
internal static class AboutTab
{
    public static View Create()
    {
        var view = new View { Title = "About", CanFocus = true, Width = Dim.Fill(), Height = Dim.Fill() };

        string built = "unknown";
        if (DateTimeOffset.TryParse(BuildInfo.BuiltUtc, CultureInfo.InvariantCulture,
                                    DateTimeStyles.AssumeUniversal, out var utc))
        {
            var local = utc.ToLocalTime();
            built = $"{local:yyyy-MM-dd HH:mm:ss zzz}   ({utc:HH:mm:ss} UTC)";
        }

        string commit = BuildInfo.Commit == "none"
            ? "none (the repository had no commits when this was built)"
            : BuildInfo.Commit + (BuildInfo.Dirty ? "   + uncommitted changes" : "");

        view.Add(
            new Label { Text = "Built", X = 2, Y = 1 },
            new Label { Text = built, X = 12, Y = 1 },
            new Label { Text = "Commit", X = 2, Y = 3 },
            new Label { Text = commit, X = 12, Y = 3 });
        return view;
    }
}
