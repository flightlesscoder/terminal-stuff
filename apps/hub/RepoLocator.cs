namespace Hub;

/// <summary>Finds the repo root at runtime by walking up from the running binary looking for a
/// marker file, rather than assuming a fixed relative depth from apps/hub/bin/.</summary>
public static class RepoLocator
{
    public static string Find()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        for (int i = 0; i < 8 && dir is not null; i++, dir = dir.Parent)
        {
            if (File.Exists(Path.Combine(dir.FullName, "setup", "setup.sh")))
                return dir.FullName;
        }
        throw new InvalidOperationException(
            $"couldn't find the repo root (looked for setup/setup.sh above {AppContext.BaseDirectory})");
    }
}
