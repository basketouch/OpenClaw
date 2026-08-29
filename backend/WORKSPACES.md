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

## Rich Notion writing

OpenClaw reads a data source schema before it creates or updates a record, so
it only fills properties that actually exist. New database records and child
pages can include real Notion blocks: headings, paragraphs, bulleted or
numbered lists, to-dos, quotes, callouts, dividers, tables and linked text.

The standard templates are `hornbills_review`, `product_update`,
`marketing_proposal`, `action` and `structured_note`. They turn named sections
into a consistent visual structure rather than storing Markdown-looking text in
a single paragraph. For example, Hornbills reviews separate findings,
hypotheses, questions and next step.

`append_notion_rich_blocks` is additive only: it appends formatted blocks to an
existing page or record and never replaces or deletes content. Updating a
record's properties remains separate from its page content. Creating a new
page and turning a note into a task still require confirmation, so an ambiguous
conversation cannot silently create structure or work.

## Deleting and moving Notion blocks

Existing blocks are changed only through a prepared plan. Alex reads the source
page, names the exact blocks and asks for `PASO 1`; it then repeats the effect
and asks for `PASO 2` in a separate user message. The plan expires after 15
minutes and can be cancelled before the second confirmation.

Page reads are paginated: when a response reports `has_more`, Alex follows its
`next_cursor` before deciding that it has seen the full page or before preparing
a block change.

Deleting sends the specified direct blocks to Notion's trash, where they remain
recoverable. Notion does not provide a direct API move for ordinary blocks, so
OpenClaw moves only compatible simple blocks by copying them to the destination
first and sending the originals to the trash only after the second confirmation.
Nested or unsupported blocks are left untouched and require a manual move in
Notion.

## Product project contexts

CutSports and DrawSports use independent restricted tool profiles and safe,
name-based destination catalogues. The catalogues contain workflow rules and
Notion destination names only; private Notion identifiers remain deployment
configuration or are resolved at runtime through search.

For both products, Alex checks the relevant project source before stating that
something is live or complete. It can read, de-duplicate and create/update
Backlog records. A release is always a proposal until Jorge explicitly confirms
publication.

DrawSports uses **Estado del Proyecto** and **Backlog — DrawSports** as the
operational source of truth. **Pendiente de publicar** holds ready-but-not-live
work, **Marketing DrawSports** holds campaigns and proposals, and **Versión
actual en App Store y web** is updated only after a verified publication. Its
sidebar shortcuts are dynamic: they surface backlog actions for work items,
release actions for publishing conversations, and marketing actions for copy or
campaign conversations.

The Analyst keeps product work separate from commercial relationships:
**Backlog — Incoherencias y Limpieza** holds concrete issues, **Roadmap —
Próximos Pasos** holds proposals that need prioritisation, and **Estado del
Proyecto** is verified before it is cited as live status. Prospects,
ambassadors, social-calendar entries and testimonials require explicit approval
before Alex creates a record; testimonial authorisation always requires clear
consent.

Comunidad keeps **Estado del Proyecto** as the verified source of truth and
**Backlog — Comunidad** for future work. **Marketing Comunidad** holds the
editorial system and funnel, while **Pendiente de publicar** is reserved for
prepared pieces with a defined channel and publishing action. Alex preserves
the distinction between Public, Comunidad, Laboratorio and VIP, and reads the
product or pricing source before it presents the current offer as fact.

Basketouch Hub is the cross-product operating context. **Acciones** is its sole
active work list; product-specific context remains in the relevant project hub.
Hub actions start in Inbox unless explicitly prioritised, and the weekly focus
is limited to five actions. The operational dashboard is the source for daily
metrics, while Notion preserves verified status, decisions, documentation and
proposals. Mockup numbers are never treated as production data.
