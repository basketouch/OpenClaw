# OpenAI migration — deployment notes

Before deploying this branch:

1. Add `OPENAI_API_KEY` to the production `.env`.
2. Add or confirm:
   - `ALEX_MODEL=gpt-5.6-luna`
   - `ALEX_COMPLEX_MODEL=gpt-5.6-terra`
   - `ENGLISH_MODEL=gpt-5.6-luna`
   - `TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe`
   - `USER_TIMEZONE=Europe/Madrid` (change to `Asia/Jakarta` when appropriate).
3. Rebuild the Docker image so `openai==2.48.0` is installed.
4. Verify `/health` before testing authenticated chat.
5. Smoke test:
   - simple chat (Luna)
   - web search/general tool
   - email/WhatsApp routing
   - NewsFlow routing
   - admin/VPS routing (Terra)
   - scheduler task
   - image and PDF attachment
6. Inspect `/data/ai_usage.jsonl` after tests.

Do not deploy without the OpenAI key: `/api/chat` and scheduled AI tasks intentionally fail clearly when the key is missing.
