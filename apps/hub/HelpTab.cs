using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace Hub;

/// <summary>Placeholder second tab so tab switching (mouse + keyboard) has something to switch to.</summary>
internal static class HelpTab
{
    public static View Create()
    {
        var view = new View { Title = "Help", CanFocus = true, Width = Dim.Fill(), Height = Dim.Fill() };
        view.Add(
            new Label { Text = "Mouse: click a tab header to switch tabs.", X = 2, Y = 1 },
            new Label { Text = "Keyboard: Tab / Shift+Tab move focus between tabs; Esc quits.", X = 2, Y = 2 },
            new Label { Text = "More tabs will be added here as this app grows.", X = 2, Y = 4 });
        return view;
    }
}
