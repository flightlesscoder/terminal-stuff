namespace Hub;

/// <summary>Idempotent marked-block file edits ("# >>> terminal-stuff:NAME >>>" ... "<<<"), the C#
/// side of setup/tui/core.py's Ctx.ensure_block/block_current/_splice -- same marker convention
/// and comment prefix, so a file either side might touch (e.g. ~/.kitty.local.conf) stays
/// compatible with both. Used by KittyThemeTab.cs; mirrors it if you add another editor here.</summary>
internal static class BlockFile
{
    static (string Begin, string End) Markers(string name, string comment) =>
        ($"{comment} >>> terminal-stuff:{name} >>>", $"{comment} <<< terminal-stuff:{name} <<<");

    /// <summary>The current block's body (trimmed), or null if the file or block doesn't exist.</summary>
    public static string? ReadBlock(string path, string name, string comment = "#")
    {
        if (!File.Exists(path)) return null;
        var (begin, end) = Markers(name, comment);
        var text = File.ReadAllText(path);
        var i = text.IndexOf(begin, StringComparison.Ordinal);
        if (i < 0) return null;
        var j = text.IndexOf(end, i, StringComparison.Ordinal);
        if (j < 0) return null;
        return text[(i + begin.Length)..j].Trim('\n', '\r');
    }

    /// <summary>Insert or replace the marked block in place, leaving everything else in the file
    /// untouched; appends if the file or block doesn't exist yet. Backs up the file (once, date-
    /// stamped) before the first change. Returns true if the file's content actually changed.</summary>
    public static bool EnsureBlock(string path, string name, string body, string comment = "#")
    {
        var (begin, end) = Markers(name, comment);
        var block = $"{begin}\n{body.Trim('\n', '\r')}\n{end}\n";
        var text = File.Exists(path) ? File.ReadAllText(path) : "";
        var i = text.IndexOf(begin, StringComparison.Ordinal);
        string newText;
        if (i >= 0)
        {
            var j = text.IndexOf(end, i, StringComparison.Ordinal);
            if (j < 0) throw new InvalidOperationException($"found '{begin}' without a matching end marker in {path}; fix it by hand");
            j += end.Length;
            if (j < text.Length && text[j] == '\n') j++;
            newText = text[..i] + block + text[j..];
        }
        else if (text.Length == 0)
        {
            newText = block;
        }
        else
        {
            var sep = text.EndsWith("\n\n") ? "" : text.EndsWith('\n') ? "\n" : "\n\n";
            newText = text + sep + block;
        }
        if (newText == text) return false;
        if (File.Exists(path))
            File.Copy(path, $"{path}.bak-{DateTime.Now:yyyyMMdd-HHmmss}", overwrite: false);
        else
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        File.WriteAllText(path, newText);
        return true;
    }
}
