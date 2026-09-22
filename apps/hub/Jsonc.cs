using System.Text.Json;
using System.Text.Json.Nodes;

namespace Hub;

/// <summary>
/// JSON-with-comments: layered search/merge and a targeted single-field editor.
/// Mirrors setup/tui/jsonc.py -- if you change one, change the other; see config/README.md for
/// the contract both implement (search order, merge rule, ${TOKEN} substitution, $replace).
/// Comment/trailing-comma parsing itself is System.Text.Json's (JsonCommentHandling.Skip); the
/// Python side hand-rolls that part since it has no such option in its stdlib json module.
/// </summary>
public static class Jsonc
{
    public const string ConfigFileName = "config.jsonc";
    public const string LocalFileName = ".terminal-stuff.jsonc";
    public const string ReplaceKey = "$replace";

    static readonly JsonNodeOptions NodeOptions = new();
    static readonly JsonDocumentOptions DocOptions = new()
    {
        CommentHandling = JsonCommentHandling.Skip,
        AllowTrailingCommas = true,
    };

    public class JsoncException(string message) : Exception(message);

    public record PathEntry(string Name, string Path);

    public record ResolvedConfig(List<PathEntry> Paths, List<string> StatusLeft, List<string> StatusRight,
                                 List<string> UsedLayers);

    public static JsonNode? Parse(string text)
    {
        try
        {
            return JsonNode.Parse(string.IsNullOrWhiteSpace(text) ? "{}" : text, NodeOptions, DocOptions);
        }
        catch (JsonException e)
        {
            throw new JsoncException($"{e.Message}");
        }
    }

    public static JsonNode? LoadFile(string path)
    {
        string text;
        try { text = File.ReadAllText(path); }
        catch (IOException e) { throw new JsoncException($"can't read {path}: {e.Message}"); }
        try { return Parse(text); }
        catch (JsoncException e) { throw new JsoncException($"{path}: {e.Message}"); }
    }

    /// <summary>object: recurse key by key. array: base's items followed by override's ("extend")
    /// -- unless override is {"$replace": [...]}, which replaces the value outright. Anything
    /// else: override wins.</summary>
    public static JsonNode? DeepMerge(JsonNode? baseNode, JsonNode? overrideNode)
    {
        if (overrideNode is JsonObject ov && ov.Count == 1 && ov.ContainsKey(ReplaceKey))
            return ov[ReplaceKey]?.DeepClone();
        if (baseNode is JsonObject bo && overrideNode is JsonObject oo)
        {
            var result = new JsonObject();
            foreach (var kv in bo) result[kv.Key] = kv.Value?.DeepClone();
            foreach (var kv in oo)
                result[kv.Key] = bo.ContainsKey(kv.Key) ? DeepMerge(bo[kv.Key], kv.Value) : kv.Value?.DeepClone();
            return result;
        }
        if (baseNode is JsonArray ba && overrideNode is JsonArray oa)
        {
            var result = new JsonArray();
            foreach (var v in ba) result.Add(v?.DeepClone());
            foreach (var v in oa) result.Add(v?.DeepClone());
            return result;
        }
        return overrideNode?.DeepClone();
    }

    public static JsonNode? SubstituteTokens(JsonNode? node, IReadOnlyDictionary<string, string> tokens)
    {
        switch (node)
        {
            case JsonValue v when v.TryGetValue<string>(out var s):
                foreach (var (k, val) in tokens) s = s.Replace($"${{{k}}}", val);
                return JsonValue.Create(s);
            case JsonObject o:
                var no = new JsonObject();
                foreach (var kv in o) no[kv.Key] = SubstituteTokens(kv.Value, tokens);
                return no;
            case JsonArray a:
                var na = new JsonArray();
                foreach (var v in a) na.Add(SubstituteTokens(v, tokens));
                return na;
            default:
                return node?.DeepClone();
        }
    }

    public static List<string> SearchPaths(string repoRoot, string cwd, string home) =>
    [
        Path.Combine(repoRoot, "config", "default.jsonc"),
        Path.Combine(home, ".config", "terminal-stuff", ConfigFileName),
        Path.Combine(cwd, LocalFileName),
    ];

    public static ResolvedConfig Resolve(string repoRoot, string cwd, string home)
    {
        var tokens = new Dictionary<string, string> { ["REPO"] = repoRoot, ["HOME"] = home };
        JsonNode? merged = new JsonObject();
        var used = new List<string>();
        foreach (var p in SearchPaths(repoRoot, cwd, home))
        {
            if (!File.Exists(p)) continue;
            var data = LoadFile(p);
            if (data is not JsonObject)
                throw new JsoncException($"{p}: top level must be a JSON object");
            merged = DeepMerge(merged, data);
            used.Add(p);
        }
        merged = SubstituteTokens(merged, tokens);
        var obj = merged as JsonObject ?? [];

        var paths = new List<PathEntry>();
        if (obj["paths"] is JsonArray pa)
            foreach (var e in pa)
                if (e is JsonObject eo && eo["name"] is JsonValue n && eo["path"] is JsonValue p)
                    paths.Add(new PathEntry(n.GetValue<string>(), p.GetValue<string>()));

        List<string> StringList(JsonNode? n) =>
            n is JsonArray arr ? [.. arr.Select(x => x?.GetValue<string>() ?? "")] : [];

        var tmux = obj["tmux"] as JsonObject;
        return new ResolvedConfig(paths, StringList(tmux?["statusLeft"]), StringList(tmux?["statusRight"]), used);
    }

    // ---------------------------------------------------------------- targeted single-field edit
    // Text surgery on one key's value so everything else in the file (comments, formatting, other
    // keys) survives untouched -- a strip-then-rewrite round trip would destroy every comment.
    // Port of setup/tui/jsonc.py's set_replace_field; keep the two in lockstep.

    static int SkipWsAndComments(string text, int i)
    {
        int n = text.Length;
        while (i < n)
        {
            char c = text[i];
            if (c is ' ' or '\t' or '\r' or '\n') { i++; }
            else if (c == '/' && i + 1 < n && text[i + 1] == '/')
            {
                int nl = text.IndexOf('\n', i);
                i = nl < 0 ? n : nl;
            }
            else if (c == '/' && i + 1 < n && text[i + 1] == '*')
            {
                int end = text.IndexOf("*/", i + 2, StringComparison.Ordinal);
                i = end < 0 ? n : end + 2;
            }
            else break;
        }
        return i;
    }

    static (int start, int end) ScanValueSpan(string text, int start)
    {
        int i = SkipWsAndComments(text, start);
        if (i >= text.Length) throw new JsoncException("unexpected end of file while scanning a value");
        char opener = text[i];
        if (opener is '{' or '[')
        {
            char closer = opener == '{' ? '}' : ']';
            int depth = 1, j = i + 1, n = text.Length;
            bool inStr = false;
            while (j < n && depth > 0)
            {
                char c = text[j];
                if (inStr)
                {
                    if (c == '\\') { j += 2; continue; }
                    if (c == '"') inStr = false;
                    j++;
                    continue;
                }
                if (c == '"') inStr = true;
                else if (c == '/' && j + 1 < n && text[j + 1] == '/')
                {
                    int nl = text.IndexOf('\n', j);
                    j = nl < 0 ? n : nl;
                    continue;
                }
                else if (c == '/' && j + 1 < n && text[j + 1] == '*')
                {
                    int end = text.IndexOf("*/", j + 2, StringComparison.Ordinal);
                    j = end < 0 ? n : end + 1;
                }
                else if (c == opener) depth++;
                else if (c == closer) depth--;
                j++;
            }
            if (depth != 0) throw new JsoncException($"unmatched '{opener}'");
            return (i, j);
        }
        if (opener == '"')
        {
            int j = i + 1;
            while (j < text.Length)
            {
                if (text[j] == '\\') { j += 2; continue; }
                if (text[j] == '"') return (i, j + 1);
                j++;
            }
            throw new JsoncException("unterminated string");
        }
        int k = i;
        while (k < text.Length && !",}] \t\r\n/".Contains(text[k])) k++;
        return (i, k);
    }

    static (int colon, int afterColon) FindKey(string text, int objStart, int objEnd, string key)
    {
        int i = objStart + 1, n = objEnd - 1;
        bool inStr = false;
        int depth = 0;
        string target = $"\"{key}\"";
        while (i < n)
        {
            char c = text[i];
            if (inStr)
            {
                if (c == '\\') { i += 2; continue; }
                if (c == '"') inStr = false;
                i++;
                continue;
            }
            if (c == '/' && i + 1 < n && text[i + 1] == '/')
            {
                int nl = text.IndexOf('\n', i);
                i = (nl < 0 || nl > n) ? n : nl;
                continue;
            }
            if (c == '/' && i + 1 < n && text[i + 1] == '*')
            {
                int end = text.IndexOf("*/", i + 2, StringComparison.Ordinal);
                i = end < 0 ? n : end + 2;
                continue;
            }
            if (c is '{' or '[') depth++;
            else if (c is '}' or ']') depth--;
            else if (c == '"')
            {
                if (depth == 0 && string.CompareOrdinal(text, i, target, 0, target.Length) == 0)
                {
                    int j = SkipWsAndComments(text, i + target.Length);
                    if (j < n && text[j] == ':') return (j, j + 1);
                }
                inStr = true;
            }
            i++;
        }
        return (-1, -1);
    }

    /// <summary>Set (inserting parent objects/keys as needed) text[keyPath...] =
    /// {"$replace": newValue}, preserving everything else byte-for-byte, comments included.</summary>
    public static string SetReplaceField(string text, IReadOnlyList<string> keyPath, JsonNode newValue)
    {
        if (string.IsNullOrWhiteSpace(text)) text = "{}";
        var (rootStart, rootEnd) = ScanValueSpan(text, 0);
        if (text[rootStart] != '{') throw new JsoncException("top level must be an object");
        int spanStart = rootStart, spanEnd = rootEnd;
        for (int depth = 0; depth < keyPath.Count; depth++)
        {
            string key = keyPath[depth];
            bool last = depth == keyPath.Count - 1;
            var wrapped = new JsonObject { [ReplaceKey] = newValue.DeepClone() };
            var (colon, valStart) = FindKey(text, spanStart, spanEnd, key);
            if (colon < 0)
            {
                int innerEnd = spanEnd - 1;                                // index of the '}'
                string before = text[(spanStart + 1)..innerEnd];
                bool needsComma = before.Trim().Length > 0;
                string insertion = $"\"{key}\": " + (last ? wrapped.ToJsonString() : "{}\n");
                string sep = needsComma ? ",\n  " : "\n  ";
                text = text[..innerEnd] + sep + insertion + (needsComma ? "\n" : "") + text[innerEnd..];
                if (last) return text;
                (colon, valStart) = FindKey(text, spanStart, spanEnd + sep.Length + insertion.Length, key);
            }
            var (vStart, vEnd) = ScanValueSpan(text, valStart);
            if (last) return text[..vStart] + wrapped.ToJsonString() + text[vEnd..];
            spanStart = vStart;
            spanEnd = vEnd;
            if (text[spanStart] != '{') throw new JsoncException($"'{key}' is not an object; can't descend into it");
        }
        return text;
    }
}
