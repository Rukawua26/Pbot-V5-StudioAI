---
name: opencode-customization
description: Use ONLY when editing or reviewing .opencode/, opencode.json, OpenCode agents, skills, commands, plugins, MCP servers, model/provider settings, or permission rules for this repository.
---

# OpenCode Customization

Keep OpenCode customization local to this repository unless the user explicitly requests global changes.

Rules:

- Preserve `$schema`: `https://opencode.ai/config.json`.
- Validate config shape against the schema before finishing.
- Do not set `model` or `small_model` here unless the user explicitly requests repo-specific models.
- Do not register the top-level `skills/` directory as an OpenCode skill path; use `.opencode/skills` only.
- Keep skill descriptions strict to avoid unnecessary activation and token use.
- Prefer reviewer agents with `edit: deny` for runtime/security review.
- Leave MCP for a later phase unless explicitly requested.
- Tell the user to restart OpenCode after config, agent, command, or skill changes.
