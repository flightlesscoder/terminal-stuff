# Terminal Stuff Hub

A tabbed TUI with mouse support (C# / .NET 10 / [Terminal.Gui](https://github.com/gui-cs/Terminal.Gui) 2.5).

- **About** tab: when this binary was built and from which git commit (`+ uncommitted changes` if the tree was dirty).
- **Help** tab: placeholder so tab switching has somewhere to go. Click a tab header or press `Tab`; `Esc` quits.

Open it from tmux: `prefix + Space`, then `h` (installed by `./setup/setup.sh`, module `hub`), or run `apps/hub/hub`.

## Build

`./setup/setup.sh` (module `hub`) does this, or by hand (needs the .NET 10 SDK):

```sh
dotnet build apps/hub -c Release -o apps/hub/bin
apps/hub/hub --about        # built: ..., commit: ..., dirty: ...
```

The build stamps the time and commit itself (see the `StampBuildInfo` target in `hub.csproj`), so the About tab
always tells you how old the binary you're looking at is. Output goes to `bin/` and `obj/` (git-ignored).

## Adding a tab

Create a `View` with a `Title` (that's the tab label) and `CanFocus = true`, fill it, and `tabs.Add(...)` it in `Program.cs`
(see `AboutTab.cs`, `HelpTab.cs`).
