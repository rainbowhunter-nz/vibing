# External Subagent Routing Guide

The `vibing-harness` MCP server dispatches work to **external subagents** — full
coding-harness runs (ADR-0013). This guide says which harness + model to pick.

## Rule of thumb (use this first)

- **cursor → `composer-2.5`** (or latest Composer): fast, cheap, strong default.
- **codex → `gpt-5.5`** (or latest GPT): autonomous CLI coding.

## Environment pins

- **codex** uses ChatGPT-account auth; its working model is **`gpt-5.5`**. The
  `-codex`-suffixed models (e.g. `gpt-5.2-codex`) are **API-key-only** and are rejected
  on a ChatGPT plan.
- **cursor** is a multi-model router. Run `cursor-agent models` for the live menu
  (Claude Opus/Sonnet/Fable, GPT-5.x, Gemini 3.x, Grok, Kimi, GLM, Composer); many ids
  carry effort/thinking/fast suffixes.

## Decision table (secondary — reach past the rule of thumb only when it matters)

| Task | Harness: model |
|---|---|
| Deep architecture / planning / hard debugging | cursor: `claude-opus-4-8-thinking-high` |
| Long-horizon autonomous multi-file refactor (CLI) | codex: `gpt-5.5` |
| Hardest large migration / multi-day run | cursor: `claude-fable-5-thinking-high` |
| Balanced day-to-day coding / test writing | cursor: `claude-4.6-sonnet-medium` |
| Frontend / UI | cursor: `claude-4.6-sonnet-medium` |
| Huge-context whole-repo analysis | cursor: `gemini-3.1-pro` |
| Fast inner-loop edits, low latency | cursor: `composer-2.5` |
| Bulk mechanical edits / classification | cursor: `gpt-5.4-mini-low` |

**Family notes (conservative, durable patterns):** Opus = deep reasoning, architecture,
review. Sonnet = balanced daily driver + frontend. Fable 5 = Anthropic's *most capable*
tier (not cheap — the cheap Claude is Haiku). GPT-5.x / codex = long-horizon CLI autonomy.
Gemini Pro = huge context; Flash = fast/cheap. Composer = low-latency fast loop, not deep
reasoning. mini/nano/flash tiers = bulk mechanical work only.

## Adding a new harness to this guide

When a harness is added to `vibing_harness`:

1. **Probe live.** Run the harness's own model-list command (e.g. `cursor-agent models`)
   and one trivial `spawn` per candidate to confirm what actually works in the target auth
   mode. Document auth-gated exclusions (as with codex `-codex` models).
2. **Add a rule-of-thumb line** (harness → best default model) above.
3. **Add decision-table rows** for the harness; note family strengths conservatively.
4. **Update the server `instructions`** rule-of-thumb list in
   `src/vibing_devcontainer_runtime/mcp_server.py` if the default choice changes.
