-- Database connections for vim-dadbod-ui (bundled by LazyVim's lang.sql extra -- see
-- setup/tui/modules/lazyvim_dev.py; no separate plugin needed). Deployed once to
-- ~/.config/nvim/lua/plugins/dadbod-connections.lua by the "lazyvim-dadbod" step, then never
-- touched again -- this is YOUR file to fill in with real connections, safe to put real
-- passwords in (unlike anything inside this repo itself): it lives outside terminal-stuff
-- entirely, in your own ~/.config/nvim, so it's never at risk of being pushed to the public repo.
--
-- Prefer $ENV_VAR expansion over literal passwords even here (one less place a secret sits in
-- plaintext, and it keeps this file diff-able/shareable between your own machines) -- dadbod
-- expands them at connect time. Export the real values from somewhere untracked, e.g. your
-- ~/.zshrc.local (see this repo's dotfiles/zsh/ for that pattern).
--
-- Open the UI with :DBUIToggle. See :help dadbod-ui and :help dadbod for full URL syntax.
return {
  {
    "tpope/vim-dadbod",
    lazy = true,
    init = function()
      vim.g.dbs = {
        -- MSSQL / Azure SQL (Azure SQL is the same sqlserver:// scheme, just Azure's hostname):
        -- { name = "mssql-local", url = "sqlserver://$MSSQL_USER:$MSSQL_PASSWORD@localhost:1433/master" },
        -- { name = "azure-sql",   url = "sqlserver://$AZ_SQL_USER:$AZ_SQL_PASSWORD@myserver.database.windows.net:1433/mydb?encrypt=true" },

        -- PostgreSQL:
        -- { name = "postgres-local", url = "postgresql://$PG_USER:$PG_PASSWORD@localhost:5432/postgres" },

        -- MongoDB:
        -- { name = "mongo-local", url = "mongodb://$MONGO_USER:$MONGO_PASSWORD@localhost:27017/mydb" },
      }
    end,
  },
}
