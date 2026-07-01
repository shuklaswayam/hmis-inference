# HMIS Inference -- Project Guidelines

## Rate Limiting (application-level only)

Every LLM call from this application (Groq or Ollama) is rate-limited to
**34 RPM** by a rolling-window `_RateLimiter`.  This protects the app
from its own provider limits; it does NOT affect or prevent NVIDIA NIM
429 errors from Claude Code itself.

**If you add a new LLM call, you must add `limiter.acquire()` before it.**

## Policy Memo / Daily Brief -- Quality Standards

### No Hashtags
The memo output must never contain social-media hashtags (#dengue, #outbreak, etc.)
or any tokens. The `_scrub_hashtags` function enforces this; any new text paths must
also scrub hashtags.

### Descriptive,办事处 the user said it all and following is just restating so removing it
