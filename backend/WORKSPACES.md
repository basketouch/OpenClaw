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

## Hornbills Technical capture

Hornbills has a separate context profile and a restricted Notion tool profile.
At the beginning of a technical session, Alex locates **Technical Area — Bogor
Hornbills** using `NOTION_HORNBILLS_HUB_PAGE_ID` when configured, or a safe
Notion search when it is not. During an active review it accumulates the
conversation instead of writing each observation independently. When Jorge
closes the session (for example, “terminamos”, “cierra”, “guárdalo” or “haz el
resumen”), Alex reads the destination, de-duplicates it and appends a dated,
non-destructive structured note.

`append_notion_note` never replaces or deletes Notion content. Creating a new
Notion page and turning a note into a task still require confirmation, so an
ambiguous conversation cannot silently create structure or work.
