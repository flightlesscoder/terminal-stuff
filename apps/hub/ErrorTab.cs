using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace Hub;

/// <summary>A tab shown in place of one that failed to build (e.g. an invalid config file), so
/// one bad file degrades gracefully instead of hub refusing to start at all.</summary>
internal static class ErrorTab
{
    public static View Create(string title, string message)
    {
        var view = new View { Title = title, CanFocus = true, Width = Dim.Fill(), Height = Dim.Fill() };
        view.Add(
            new Label { Text = $"Couldn't load {title}:", X = 2, Y = 1 },
            new Label { Text = message, X = 2, Y = 3 },
            new Label { Text = "Fix it and restart hub. ./setup/doctor.sh also reports config errors.", X = 2, Y = 5 });
        return view;
    }
}
