using System.Collections.ObjectModel;
using System.Text.Json;
using Terminal.Gui.App;
using Terminal.Gui.Drawing;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace Hub;

/// <summary>Same information `./setup/doctor.sh` reports, with the option to actually run/install
/// any of it -- a UI on top of `setup/setup.sh --list/--run --json` (see SetupModel.cs). Never
/// reimplements install logic here; Python via setup.sh stays the one place that lives.</summary>
internal static class SetupTab
{
    public static View Create(string repoRoot, IApplication app)
    {
        var view = new View { Title = "Setup", CanFocus = true, Width = Dim.Fill(), Height = Dim.Fill() };

        List<SetupModel.ModuleInfo> modules = [];
        int selectedModuleIdx = -1;
        (SetupModel.ModuleInfo Module, int Index)? activeStep = null;
        bool running = false;
        var cts = new System.Threading.CancellationTokenSource();

        var osLabel = new Label { X = 1, Y = 0, Width = Dim.Fill(1), Text = "loading..." };
        var moduleList = new ListView { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill() };
        var moduleNames = new ObservableCollection<string>();
        moduleList.SetSource(moduleNames);
        var modulePane = new View { Title = "Modules", X = 0, Y = 1, Width = 34, Height = Dim.Fill(9), BorderStyle = LineStyle.Single };
        modulePane.Add(moduleList);

        var stepList = new ListView { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill() };
        var stepRows = new ObservableCollection<string>();
        stepList.SetSource(stepRows);
        var stepPane = new View { Title = "Steps", X = Pos.Right(modulePane), Y = 1, Width = Dim.Fill(), Height = Dim.Fill(9), BorderStyle = LineStyle.Single };
        stepPane.Add(stepList);

        var moduleDesc = new Label { X = 1, Y = Pos.Bottom(modulePane), Width = Dim.Fill(1), Height = 2, Text = "" };

        var dryRunBox = new CheckBox { Text = "Dry run", X = 1, Y = Pos.Bottom(moduleDesc) };
        var runStepBtn = new Button { Text = "Run Step", X = Pos.Right(dryRunBox) + 2, Y = Pos.Top(dryRunBox) };
        var runModuleBtn = new Button { Text = "Run All Todo In Module", X = Pos.Right(runStepBtn) + 1, Y = Pos.Top(dryRunBox) };
        var refreshBtn = new Button { Text = "Refresh", X = Pos.Right(runModuleBtn) + 1, Y = Pos.Top(dryRunBox) };
        var cancelBtn = new Button { Text = "Cancel", X = Pos.Right(refreshBtn) + 1, Y = Pos.Top(dryRunBox), Enabled = false };

        var status = new Label { X = 1, Y = Pos.Bottom(dryRunBox) + 1, Width = Dim.Fill(1), Text = "" };
        var outputPane = new View { Title = "Output", X = 0, Y = Pos.Bottom(status) + 1, Width = Dim.Fill(), Height = Dim.Fill(), BorderStyle = LineStyle.Single };
        var output = new TextView { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(), ReadOnly = true, WordWrap = false };
        outputPane.Add(output);

        void AppendOutput(string line)
        {
            output.Text = output.Text.Length > 0 ? output.Text + "\n" + line : line;
            var lines = output.Text.Split('\n');
            output.ScrollTo(new System.Drawing.Point(0, Math.Max(0, lines.Length - 1)));
        }

        void ShowSteps(int idx)
        {
            selectedModuleIdx = idx;
            stepRows.Clear();
            activeStep = null;
            if (idx < 0 || idx >= modules.Count) { moduleDesc.Text = ""; return; }
            var m = modules[idx];
            moduleDesc.Text = m.Description;
            foreach (var s in m.Steps)
            {
                string mark = s.State switch { "done" => "✔", "todo" => "·", "unsupported" => "-", _ => "?" };
                string sudo = s.NeedsSudo ? " [sudo]" : "";
                stepRows.Add($"{mark} {s.Title}{sudo}");
            }
        }

        void Reload()
        {
            try
            {
                var result = SetupModel.List(repoRoot);
                osLabel.Text = result.Os;
                modules = result.Modules;
                moduleNames.Clear();
                foreach (var m in modules) moduleNames.Add($"{m.Id} ({m.Steps.Count(s => s.State == "todo")} todo)");
                var keep = Math.Clamp(selectedModuleIdx, 0, Math.Max(0, modules.Count - 1));
                moduleList.SetSelection(keep, false);
                ShowSteps(modules.Count > 0 ? keep : -1);
                status.Text = $"loaded {modules.Count} modules  ·  log: {result.Log}";
            }
            catch (Exception e)
            {
                status.Text = $"couldn't load setup state: {e.Message}";
            }
        }

        moduleList.ValueChanged += (_, e) => { if (e.NewValue is int i) ShowSteps(i); };
        moduleList.MouseEvent += (_, __) => { if (moduleList.SelectedItem is int i) ShowSteps(i); };
        stepList.ValueChanged += (_, e) => { if (e.NewValue is int i && selectedModuleIdx >= 0) activeStep = (modules[selectedModuleIdx], i); };
        stepList.MouseEvent += (_, __) => { if (stepList.SelectedItem is int i && selectedModuleIdx >= 0) activeStep = (modules[selectedModuleIdx], i); };

        void SetRunning(bool r)
        {
            running = r;
            runStepBtn.Enabled = !r;
            runModuleBtn.Enabled = !r;
            refreshBtn.Enabled = !r;
            moduleList.Enabled = !r;
            stepList.Enabled = !r;
            cancelBtn.Enabled = r;
        }

        void HandleEvent(JsonElement ev)
        {
            var kind = ev.GetProperty("event").GetString();
            switch (kind)
            {
                case "start":
                    AppendOutput($"==> {ev.GetProperty("step").GetString()}: {ev.GetProperty("title").GetString()}");
                    break;
                case "output":
                    AppendOutput("    " + ev.GetProperty("line").GetString());
                    break;
                case "end":
                    var st = ev.GetProperty("status").GetString();
                    var detail = ev.GetProperty("detail").GetString();
                    AppendOutput($"    [{st}] {detail}");
                    break;
                case "summary":
                    if (ev.TryGetProperty("nothing_to_do", out _))
                        AppendOutput("(nothing to do)");
                    else
                        AppendOutput($"-- {ev.GetProperty("ok").GetInt32()} ok, {ev.GetProperty("failed").GetInt32()} failed, {ev.GetProperty("skipped").GetInt32()} skipped");
                    break;
                case "error":
                    AppendOutput("ERROR: " + ev.GetProperty("message").GetString());
                    break;
            }
        }

        void RunAsync(string moduleId, List<string>? stepIds)
        {
            if (running) return;
            SetRunning(true);
            output.Text = "";
            status.Text = $"running {moduleId}" + (stepIds is { Count: > 0 } ? $" ({string.Join(',', stepIds)})" : "") + "...";
            bool dry = dryRunBox.Value == CheckState.Checked;
            var localCts = new System.Threading.CancellationTokenSource();
            cts = localCts;

            System.Threading.Tasks.Task.Run(() =>
            {
                int exit = -1;
                Exception? failure = null;
                try
                {
                    exit = SetupModel.Run(repoRoot, moduleId, stepIds, dry, ev =>
                        app.Invoke(() => HandleEvent(ev)), localCts.Token);
                }
                catch (Exception e) { failure = e; }
                app.Invoke(() =>
                {
                    SetRunning(false);
                    status.Text = failure is not null ? $"failed to run: {failure.Message}"
                                : localCts.IsCancellationRequested ? "cancelled"
                                : $"finished (exit {exit})";
                    Reload();
                });
            });
        }

        runStepBtn.Accepting += (_, __) =>
        {
            if (activeStep is not var (m, i) || i < 0 || i >= m.Steps.Count) { status.Text = "select a step first"; return; }
            RunAsync(m.Id, [m.Steps[i].Id]);
        };
        runModuleBtn.Accepting += (_, __) =>
        {
            if (selectedModuleIdx < 0 || selectedModuleIdx >= modules.Count) { status.Text = "select a module first"; return; }
            RunAsync(modules[selectedModuleIdx].Id, null);        // null = Python's own default (todo) selection
        };
        refreshBtn.Accepting += (_, __) => Reload();
        cancelBtn.Accepting += (_, __) => cts.Cancel();

        Reload();
        view.Add(osLabel, modulePane, stepPane, moduleDesc, dryRunBox, runStepBtn, runModuleBtn, refreshBtn, cancelBtn, status, outputPane);
        return view;
    }
}
