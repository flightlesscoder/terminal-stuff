using System.Diagnostics;
using Terminal.Gui.App;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace Hub;

/// <summary>Deploy, configure and mute ~/apps/scripts/speak-background.sh. One editable args field
/// per engine (the script holds all of them at once so it stays portable between machines); the
/// one actually used here is whichever DetectEngine() picks, shown at the top.</summary>
internal static class SpeechTab
{
    public static View Create(string repoRoot, string home)
    {
        var view = new View { Title = "Speech", CanFocus = true, Width = Dim.Fill(), Height = Dim.Fill() };
        string scriptPath = Path.Combine(home, "apps", "scripts", "speak-background.sh");
        string templatePath = Path.Combine(repoRoot, "dotfiles", "scripts", "speak-background.sh");

        var pathLabel = new Label { X = 1, Y = 0, Width = Dim.Fill(1), Text = scriptPath };
        var statusLabel = new Label { X = 1, Y = 1, Width = Dim.Fill(1), Text = "" };
        var createBtn = new Button { Text = "Create", X = 1, Y = 2 };
        var muteBtn = new Button { Text = "Toggle Mute", X = Pos.Right(createBtn) + 1, Y = 2 };
        var testBtn = new Button { Text = "Test: speak a sample phrase", X = Pos.Right(muteBtn) + 1, Y = 2 };

        var fieldsTop = 4;
        var labelWidth = 26;
        var fields = new Dictionary<string, TextField>();
        for (int i = 0; i < SpeechScript.ArgFields.Length; i++)
        {
            var (label, varName) = SpeechScript.ArgFields[i];
            var y = fieldsTop + i;
            var lbl = new Label { X = 1, Y = y, Width = labelWidth, Text = label };
            var tf = new TextField { X = 1 + labelWidth, Y = y, Width = Dim.Fill(1), Text = "" };
            fields[varName] = tf;
            view.Add(lbl, tf);
        }

        var saveBtn = new Button { Text = "Save", X = 1, Y = fieldsTop + SpeechScript.ArgFields.Length + 1, IsDefault = true };
        var revertBtn = new Button { Text = "Revert", X = Pos.Right(saveBtn) + 1, Y = Pos.Top(saveBtn) };
        var status = new Label { X = 1, Y = Pos.Bottom(saveBtn) + 1, Width = Dim.Fill(1), Text = "" };
        var hint = new Label
        {
            X = 1, Y = Pos.AnchorEnd(1), Width = Dim.Fill(1),
            Text = "Args use shell-like quoting, e.g.: -v \"Samantha (Enhanced)\" -r 175   (find macOS voice names with: say -v ?)",
        };

        void Refresh()
        {
            var st = SpeechScript.GetStatus(scriptPath, home);
            statusLabel.Text = st.Exists
                ? $"engine on this machine: {st.Engine}    |    {(st.Muted ? "MUTED" : "unmuted")}" + (st.Executable ? "" : "  (not executable!)")
                : $"not installed yet -- click Create (engine on this machine would be: {st.Engine})";
            muteBtn.Text = st.Exists && st.Muted ? "Unmute" : "Mute";
            muteBtn.Enabled = st.Exists;
            testBtn.Enabled = st.Exists;
            foreach (var (_, varName) in SpeechScript.ArgFields)
                fields[varName].Text = st.Exists ? SpeechScript.ReadArgsDisplay(scriptPath, varName) : "";
        }

        createBtn.Accepting += (_, __) =>
        {
            try
            {
                if (File.Exists(scriptPath)) { status.Text = "already exists"; return; }
                Directory.CreateDirectory(Path.GetDirectoryName(scriptPath)!);
                File.Copy(templatePath, scriptPath);
                if (!OperatingSystem.IsWindows())
                    File.SetUnixFileMode(scriptPath, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute
                        | UnixFileMode.GroupRead | UnixFileMode.GroupExecute | UnixFileMode.OtherRead | UnixFileMode.OtherExecute);
                status.Text = $"created {scriptPath}";
            }
            catch (Exception e) { status.Text = $"create failed: {e.Message}"; }
            Refresh();
        };

        muteBtn.Accepting += (_, __) =>
        {
            try
            {
                bool nowMuted = SpeechScript.ToggleMute(scriptPath);
                status.Text = nowMuted ? "muted" : "unmuted";
            }
            catch (Exception e) { status.Text = $"toggle failed: {e.Message}"; }
            Refresh();
        };

        saveBtn.Accepting += (_, __) =>
        {
            try
            {
                foreach (var (_, varName) in SpeechScript.ArgFields)
                    SpeechScript.WriteArgs(scriptPath, varName, fields[varName].Text ?? "");
                status.Text = "saved";
            }
            catch (Exception e) { status.Text = $"save failed: {e.Message}"; }
            Refresh();
        };

        revertBtn.Accepting += (_, __) => { Refresh(); status.Text = "reverted (unsaved edits discarded)"; };

        testBtn.Accepting += (_, __) =>
        {
            try
            {
                var st = SpeechScript.GetStatus(scriptPath, home);
                var psi = new ProcessStartInfo(scriptPath)
                {
                    ArgumentList = { "This", "is", "a", "test", "of", "the", "speech", "configuration." },
                    RedirectStandardError = true,
                };
                using var proc = Process.Start(psi) ?? throw new InvalidOperationException("couldn't start the script");
                proc.WaitForExit(3000);
                status.Text = st.Muted ? "ran (muted, so silent by design)" : "spoke it -- did you hear it?";
            }
            catch (Exception e) { status.Text = $"test failed: {e.Message}"; }
        };

        Refresh();
        view.Add(pathLabel, statusLabel, createBtn, muteBtn, testBtn, saveBtn, revertBtn, status, hint);
        return view;
    }
}
