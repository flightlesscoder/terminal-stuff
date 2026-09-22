using System.Diagnostics;
using System.Text.Json;

namespace Hub;

/// <summary>Talks to setup/setup.sh --json (never re-implements install logic in C# -- Python
/// stays the single source of truth for everything installable; hub is just a UI on top of it).</summary>
public static class SetupModel
{
    public record StepInfo(string Id, string Title, string Description, bool NeedsSudo, bool Default,
                           string State, string Detail);
    public record ModuleInfo(string Id, string Title, string Description, List<StepInfo> Steps);
    public record ListResult(string Os, string Log, List<ModuleInfo> Modules);

    static string ScriptPath(string repoRoot) => Path.Combine(repoRoot, "setup", "setup.sh");

    public static ListResult List(string repoRoot)
    {
        var psi = new ProcessStartInfo(ScriptPath(repoRoot), "--list --json")
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = repoRoot,
        };
        using var proc = Process.Start(psi) ?? throw new InvalidOperationException("couldn't start setup.sh");
        string stdout = proc.StandardOutput.ReadToEnd();
        string stderr = proc.StandardError.ReadToEnd();
        proc.WaitForExit(30000);
        if (proc.ExitCode != 0 || string.IsNullOrWhiteSpace(stdout))
            throw new InvalidOperationException($"setup.sh --list --json failed (exit {proc.ExitCode}): {stderr}");

        using var doc = JsonDocument.Parse(stdout);
        var root = doc.RootElement;
        var modules = new List<ModuleInfo>();
        foreach (var m in root.GetProperty("modules").EnumerateArray())
        {
            var steps = new List<StepInfo>();
            foreach (var s in m.GetProperty("steps").EnumerateArray())
            {
                steps.Add(new StepInfo(
                    s.GetProperty("id").GetString() ?? "",
                    s.GetProperty("title").GetString() ?? "",
                    s.GetProperty("description").GetString() ?? "",
                    s.GetProperty("needs_sudo").GetBoolean(),
                    s.GetProperty("default").GetBoolean(),
                    s.GetProperty("state").GetString() ?? "",
                    s.GetProperty("detail").GetString() ?? ""));
            }
            modules.Add(new ModuleInfo(m.GetProperty("id").GetString() ?? "", m.GetProperty("title").GetString() ?? "",
                m.GetProperty("description").GetString() ?? "", steps));
        }
        return new ListResult(root.GetProperty("os").GetString() ?? "", root.GetProperty("log").GetString() ?? "", modules);
    }

    /// <summary>Runs `setup.sh --run module [--steps ids] [--dry-run] --yes --json`, calling
    /// onEvent for each JSON-lines event as it arrives (NOT batched -- the caller sees output
    /// live). Runs on the calling thread; callers wanting a responsive UI should call this from a
    /// background Task and marshal onEvent's work back via Application.Invoke themselves.</summary>
    public static int Run(string repoRoot, string moduleId, IReadOnlyList<string>? stepIds, bool dryRun,
                          Action<JsonElement> onEvent, CancellationToken cancel)
    {
        var args = $"--run {moduleId} --yes --json";
        if (stepIds is { Count: > 0 }) args += $" --steps {string.Join(',', stepIds)}";
        if (dryRun) args += " --dry-run";
        var psi = new ProcessStartInfo(ScriptPath(repoRoot), args)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = repoRoot,
        };
        using var proc = Process.Start(psi) ?? throw new InvalidOperationException("couldn't start setup.sh");
        using var reg = cancel.Register(() => { try { proc.Kill(entireProcessTree: true); } catch { } });
        string? line;
        while ((line = proc.StandardOutput.ReadLine()) != null)
        {
            if (cancel.IsCancellationRequested) break;
            if (string.IsNullOrWhiteSpace(line)) continue;
            try
            {
                using var doc = JsonDocument.Parse(line);
                onEvent(doc.RootElement.Clone());
            }
            catch (JsonException)
            {
                // A non-JSON line on stdout shouldn't be possible in --json mode, but never let a
                // parse hiccup take the whole run down -- surface it as a synthetic output event.
                onEvent(JsonDocument.Parse($"{{\"event\":\"output\",\"line\":{JsonSerializer.Serialize(line)}}}").RootElement.Clone());
            }
        }
        proc.WaitForExit();
        return proc.ExitCode;
    }
}
