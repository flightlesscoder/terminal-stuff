-- Bash and PowerShell LSPs: neither has an official LazyVim extra (unlike TypeScript/Python/
-- C#/SQL/JSON, which are enabled via ~/.config/nvim/lazyvim.json's "extras" list instead -- see
-- setup/tui/modules/lazyvim_dev.py). This is a plain custom plugin spec, deployed once to
-- ~/.config/nvim/lua/plugins/extra-langs.lua by the "lazyvim-extra-langs" step (never overwritten
-- after that, so your own edits stick -- delete the file and re-run the step to reset it).
--
-- Follows the same opts-merging pattern LazyVim's own lang extras use, so `:Lazy sync` installs
-- the servers via mason and lspconfig picks them up automatically.
return {
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        bashls = {},
        powershell_es = {
          bundle_path = vim.fn.stdpath("data") .. "/mason/packages/powershell-editor-services",
        },
      },
    },
  },
  {
    "WhoIsSethDaniel/mason-tool-installer.nvim",
    opts = function(_, opts)
      opts.ensure_installed = opts.ensure_installed or {}
      vim.list_extend(opts.ensure_installed, { "bash-language-server", "powershell-editor-services" })
    end,
  },
}
