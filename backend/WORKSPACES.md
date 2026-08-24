# Workspaces and projects

OpenClaw stores the navigation scope with every conversation:

```json
{
  "workspace_id": "projects",
  "project_id": "cutsports",
  "scope_source": "auto"
}
```

`workspace_id` is one of `general`, `hornbills`, `english`, or `projects`.
`project_id` is optional and is valid only inside `projects`: `cutsports`,
`drawsports`, `the-analyst`, `comunidad`, or `basketouch-hub`.

## Migration

There is no separate migration command. On the next `GET /api/chats` (or opening
an individual chat), older JSON chat records are upgraded in place. Any record
without a valid scope is assigned to `general`, so no existing conversation is
lost or hidden.

## Routing and reassignment

New, unassigned conversations begin in General. On the first message the backend
uses a fast deterministic context router. It recognizes the configured projects,
Hornbills and English; an automatically selected scope persists for subsequent
messages in that conversation. The user can move a conversation from its scope
label in the header at any time. A manual selection is never overwritten by the
router.

The sidebar exposes a compact Recent section (five most recently updated chats)
as well as the complete nested hierarchy. Recent is a shortcut, not a duplicate
storage location.

## Memory and tools hooks

The workspace catalogue contains `instruction_hook` values, and the chat request
carries the active workspace/project. `chat.py` passes that scope to the
instruction builder through a deliberately small hook. Future workspace-specific
instructions, memory retrieval and tool profiles belong there (or in a dedicated
context service), never in frontend/sidebar rendering code.
