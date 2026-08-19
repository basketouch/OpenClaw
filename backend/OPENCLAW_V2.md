# OpenClaw v2 — AI core

## Goals

- One AI provider: OpenAI.
- Responses API for chat, reasoning and function calling.
- Low-cost default model with deterministic escalation for complex work.
- Tool profiles so the model only sees tools relevant to the current task.
- Configurable user timezone.
- Enough conversation context to avoid short-term amnesia.
- Local usage logging for later cost/reliability analysis.

## Models

- `ALEX_MODEL=gpt-5.6-luna`: default workload.
- `ALEX_COMPLEX_MODEL=gpt-5.6-terra`: admin, coding and complex analysis.
- `ENGLISH_MODEL=gpt-5.6-luna`: English Coach.
- `TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe`: future audio capture.

## Routing

Current routing is intentionally deterministic. Requests are classified into:

- `general`
- `communications`
- `newsflow`
- `admin`
- `english`

This avoids an extra model call just to choose a model/tool set.

## Tools

Tool profiles are defined in `tools/registry.py`. The general assistant no longer receives every available tool on every request.

## Context

The web client sends the most recent 16 messages. The backend also caps input to 16 messages. A later phase will replace this fixed window with recent messages + conversation summary + relevant long-term memory.

## Privacy and state

Responses are created with `store=False`. Conversation history remains in OpenClaw's local `/data/chats` storage.

## Observability

AI usage metadata is appended to `/data/ai_usage.jsonl`, including model, routed mode, tool profile, elapsed time and API usage metadata.

## Next phases

1. Add conversation summaries and user/project memory.
2. Build English Coach memory and Notion sync.
3. Add audio upload/transcription.
4. Add review/spaced-repetition engine.
5. Add model/tool reliability metrics to the admin UI.
