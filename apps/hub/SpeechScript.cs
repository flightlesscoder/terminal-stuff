using System.Text;
using System.Text.RegularExpressions;

namespace Hub;

/// <summary>Reads/edits ~/apps/scripts/speak-background.sh: the per-engine `NAME=(...)` argument
/// lines and the SPEAK-LINE mute toggle. Whole-line regex replace (same idea as core.py's
/// FONT_LINE_RE/hyper_font_run in the Python side), not a general bash parser -- this only needs
/// to handle the exact shapes dotfiles/scripts/speak-background.sh itself uses.</summary>
public static class SpeechScript
{
    public const string SpeakLine = "_speak_now \"$TEXT\" &";

    public record Status(bool Exists, bool Executable, bool Muted, string Engine);

    // Engine field -> the bash variable that holds its args array in the script.
    public static readonly (string Label, string VarName)[] ArgFields =
    [
        ("macOS say", "SAY_ARGS"),
        ("Linux spd-say", "SPD_SAY_ARGS"),
        ("Linux espeak-ng", "ESPEAK_NG_ARGS"),
        ("Linux festival", "FESTIVAL_ARGS"),
        ("Linux flite", "FLITE_ARGS"),
        ("Windows rate (-10..10)", "POWERSHELL_RATE"),
        ("Windows volume (0-100)", "POWERSHELL_VOLUME"),
    ];

    public static string DetectEngine(string home)
    {
        if (OperatingSystem.IsMacOS()) return "say";
        if (OperatingSystem.IsWindows()) return "powershell";
        foreach (var e in new[] { "spd-say", "espeak-ng", "festival", "flite" })
            if (OnPath(e)) return e;
        return OnPath("powershell.exe") || OnPath("pwsh") ? "powershell" : "none";
    }

    static bool OnPath(string exe)
    {
        var path = Environment.GetEnvironmentVariable("PATH") ?? "";
        return path.Split(Path.PathSeparator).Any(dir =>
            !string.IsNullOrEmpty(dir) && File.Exists(Path.Combine(dir, exe)));
    }

    public static Status GetStatus(string scriptPath, string home)
    {
        if (!File.Exists(scriptPath)) return new Status(false, false, false, DetectEngine(home));
        bool exec = OperatingSystem.IsWindows()
                   || (File.GetUnixFileMode(scriptPath) & UnixFileMode.UserExecute) != 0;
        var text = File.ReadAllText(scriptPath);
        bool muted = Regex.IsMatch(text, @"^\s*#\s*" + Regex.Escape(SpeakLine), RegexOptions.Multiline);
        return new Status(true, exec, muted, DetectEngine(home));
    }

    public static bool ToggleMute(string scriptPath)
    {
        var text = File.ReadAllText(scriptPath);
        var commented = new Regex(@"^(\s*)#\s*" + Regex.Escape(SpeakLine) + @"\s*$", RegexOptions.Multiline);
        var plain = new Regex(@"^(\s*)" + Regex.Escape(SpeakLine) + @"\s*$", RegexOptions.Multiline);
        if (commented.IsMatch(text))
        {
            File.WriteAllText(scriptPath, commented.Replace(text, m => $"{m.Groups[1].Value}{SpeakLine}", 1));
            return false;                                          // now unmuted
        }
        if (plain.IsMatch(text))
        {
            File.WriteAllText(scriptPath, plain.Replace(text, m => $"{m.Groups[1].Value}# {SpeakLine}", 1));
            return true;                                           // now muted
        }
        throw new InvalidOperationException("SPEAK-LINE not found in the script (edited incompatibly?)");
    }

    /// <summary>Current args for `varName` as a human-editable string, e.g. -v "Samantha (Enhanced)" -r 175.</summary>
    public static string ReadArgsDisplay(string scriptPath, string varName)
    {
        if (!File.Exists(scriptPath)) return "";
        var span = FindArraySpan(File.ReadAllText(scriptPath), varName);
        return span is var (text, inner) ? ToDisplay(Tokenize(text.Substring(inner.start, inner.end - inner.start))) : "";
    }

    /// <summary>Write `display` (parsed the same way, e.g. `-v "a b"` -> one token `a b`) into
    /// varName's line, replacing from `VARNAME=(` through the end of that source line (so a
    /// trailing "e.g.: ..." example comment is dropped -- it'd be stale once you've set a real
    /// value anyway).</summary>
    public static void WriteArgs(string scriptPath, string varName, string display)
    {
        var tokens = Tokenize(display);
        var literal = $"{varName}=({string.Join(' ', tokens.Select(Quote))})";
        var text = File.ReadAllText(scriptPath);
        if (FindArraySpan(text, varName) is not var (_, span))
            throw new InvalidOperationException($"{varName} not found in the script (edited incompatibly?)");
        int lineStart = text.LastIndexOf('\n', Math.Max(span.start - 1, 0)) + 1;
        int lineEnd = text.IndexOf('\n', span.end);
        if (lineEnd < 0) lineEnd = text.Length;
        File.WriteAllText(scriptPath, text[..lineStart] + literal + text[lineEnd..]);
    }

    /// <summary>(text, (start, end)) where text[start..end] is the content between VARNAME='s `(`
    /// and its matching `)`, found by depth+quote-aware scanning (NOT a greedy/lazy regex -- a
    /// trailing same-line comment like `# e.g.: SAY_ARGS=(-v "x (y)" -r 175)` has its own parens,
    /// and a real value can itself contain a paren, e.g. a voice named "Samantha (Enhanced)").</summary>
    static (string text, (int start, int end))? FindArraySpan(string text, string varName)
    {
        var head = Regex.Match(text, $@"^{Regex.Escape(varName)}=\(", RegexOptions.Multiline);
        if (!head.Success) return null;
        int i = head.Index + head.Length, start = i, depth = 1, n = text.Length;
        bool inQuotes = false;
        while (i < n && depth > 0)
        {
            char c = text[i];
            if (inQuotes)
            {
                if (c == '\\' && i + 1 < n) { i += 2; continue; }
                if (c == '"') inQuotes = false;
                i++;
                continue;
            }
            if (c == '"') inQuotes = true;
            else if (c == '(') depth++;
            else if (c == ')') depth--;
            i++;
        }
        if (depth != 0) throw new InvalidOperationException($"unmatched '(' for {varName}");
        return (text, (start, i - 1));
    }

    // ---------------------------------------------------------------- tokenizing (shared by both
    // "parse what's between the ( and )" and "parse what the user typed into the text field")

    public static List<string> Tokenize(string s)
    {
        var tokens = new List<string>();
        var cur = new StringBuilder();
        bool inTok = false, inQuotes = false;
        for (int i = 0; i < s.Length; i++)
        {
            char c = s[i];
            if (inQuotes)
            {
                if (c == '\\' && i + 1 < s.Length && s[i + 1] is '"' or '\\') { cur.Append(s[++i]); continue; }
                if (c == '"') { inQuotes = false; continue; }
                cur.Append(c);
                continue;
            }
            if (c == '"') { inQuotes = true; inTok = true; continue; }
            if (char.IsWhiteSpace(c))
            {
                if (inTok) { tokens.Add(cur.ToString()); cur.Clear(); inTok = false; }
                continue;
            }
            inTok = true;
            cur.Append(c);
        }
        if (inTok) tokens.Add(cur.ToString());
        return tokens;
    }

    static string Quote(string tok) =>
        tok.Length == 0 || tok.Any(char.IsWhiteSpace)
            ? "\"" + tok.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\""
            : tok;

    public static string ToDisplay(List<string> tokens) => string.Join(' ', tokens.Select(Quote));
}
