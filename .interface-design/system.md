# OpenClaw interface system

## Direction

Alex is a private operational companion used between training, travel and desk
work. The interface should feel like a focused working notebook: calm, direct
and reliable rather than like a generic assistant demo.

## Visual foundations

- **Palette:** charcoal base and surfaces, restrained violet for deliberate
  actions and active states, red only for recording or destructive actions,
  pale text for content and muted lavender for secondary status.
- **Depth:** borders-first. Use quiet borders and small surface shifts; avoid
  decorative shadows and gradients.
- **Typography:** system UI font for fast, natural reading on iPhone and Mac.
- **Spacing:** 4px base unit. Keep controls compact but with touch targets of
  at least 34px.

## Conversation controls

- The message field is the primary work surface. Audio and attachment controls
  sit alongside it, never behind a separate screen.
- Voice uses one WhatsApp-style microphone gesture instead of a persistent
  mode: a brief touch starts reviewed dictation; holding for 0.35 seconds starts
  a voice turn, releasing sends it and Alex reads the reply aloud. Sliding away
  before release cancels the voice turn.
- Every voice turn remains visible as text in the chat. Generated speech is
  always labelled `Voz IA` and may be replayed or stopped by the user.
- Reviewed dictation never plays speech automatically; it stays editable until
  the user chooses to send it.

## Reusable patterns

- A violet active state represents an intentional, persistent mode.
- Red is reserved for a live recording state, never used as decoration.
- Voice status is short, adjacent to the composer and describes the immediate
  state: listening, transcribing, sending or ready to review.
