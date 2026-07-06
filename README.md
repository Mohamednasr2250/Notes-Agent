# Notes Agent

A chat agent for managing notes using plain English: add, search, update,
delete, undo, and ask questions about your notes. Examples below use a
property/repairs theme, but it works for any kind of note.

**See `DEMO.md` for real conversations, unedited, including two bonus
features actually working.**

## How to run it

**Recommended: with a real AI model (Hugging Face, free, no card needed —
this is the provider actually used to build and test this project).**

```bash
cd notes_agent
```
If you don't already have a `.env` file, create one from the template:
```bash
copy .env.example .env
```
Open `.env` and add your Hugging Face token (`HF_TOKEN=...`) — get one free
at huggingface.co under Settings -> Access Tokens. Then:
```bash
python -m notes_agent.cli
```

**Without any setup:** it also runs with no API key at all, using a
built-in offline mode instead of a real AI model — useful for a quick
look, but Hugging Face is the way to see it actually understanding real
sentences. Azure OpenAI is also supported (`LLM_PROVIDER=azure_openai` +
the matching keys in `.env`), documented as the natural fit for TechLabs'
Microsoft stack, though Hugging Face is what this was actually built and
tested against.

Run the automated tests:
```bash
python tests/eval_harness.py
```

## Files

```
notes_agent/
  storage.py       saves notes in a local database file
  tools.py         the actions the agent can take (add, search, update, delete, undo...)
  llm_providers.py connects to the AI model (Azure OpenAI, Hugging Face, or offline mode)
  agent.py         runs the conversation and keeps things safe
  cli.py           the chat window you type into
tests/eval_harness.py   17 automated tests
bonus/                  extra features below
toolschemadocumentation.md                list of every action the agent can take
DEMO.md                 real conversations, unedited
```

## Everything the agent can do

**Core actions (the main task requirements):**
- **Add a note** — title, body, and optional tags, all pulled from one
  normal sentence.
- **Search and list notes** — by keyword, by tag, or both.
- **Update a note** — title, body, and/or tags.
- **Delete a note**.
- **Answer questions about your notes** — summarise a tag, or spot when
  two notes contradict each other (see `DEMO.md` for a real example of
  this happening).

**Required behaviours:**
- **Ask which note you mean, if more than one matches** — there's no
  "delete by keyword" action, only by exact ID, so the agent has to
  search first and ask if more than one note comes back.
- **Confirm before deleting or changing something** — checked directly in
  the code (`agent.py`), not just asked of the AI model, so it can't
  happen by accident even if the model gets confused.
- **Remember what you just talked about** — so "add a deadline to that"
  works without repeating yourself or the note's name again.
- **Say clearly when nothing is found**, and suggest what to try instead,
  instead of just going quiet or making something up.
- **Automated tests** — `tests/eval_harness.py`, 17 tests, all passing.

**Extra things this project also does, beyond what was asked:**
- **Undo** — say "undo" and the last add, update, or delete gets reversed.
- **Recurring issue detection** — checks a tag (like "maintenance") for
  the same word showing up in more than one note, e.g. spotting "boiler"
  or "radiator" across several separate repair notes.
- **Multi-user isolation** — every note is tied to a user ID, and every
  part of the code filters by it, so two different users genuinely can't
  see each other's notes, even sharing the same database file. Tested
  directly with two real users (see `DEMO.md`).
- **MCP + LangGraph** — the same notes actions, exposed through the MCP
  standard, driven by a LangGraph agent instead of the normal chat loop.
  Tested and working (see `DEMO.md`).
- **Semantic search + LangGraph** — finds notes by meaning, not just
  exact words. Tested and working, with a real similarity score to prove
  it (see `DEMO.md`).





## Why a database file instead of a plain text/JSON file

A real database (SQLite) makes searching and filtering easier, and won't
get corrupted if the program closes unexpectedly mid-save. A plain JSON
file would also work fine for this size of project — this was just the
slightly sturdier choice, not because JSON is a bad option.

## How it keeps you safe from mistakes

Deleting or changing a note always asks you to confirm first — and this
confirmation is checked directly in the code, not just something the AI
model was told to do. That way, even if the model gets confused, it can't
delete or change something without you actually saying yes.

If you say "undo," the last thing you did (add, update, or delete) gets
reversed.

## Bonus features — all tested and working for real

- **MCP + LangGraph**: the same notes tools, exposed through the MCP
  standard and run by a LangGraph agent instead of the normal chat loop.
  Actually tested — it saved real notes (#9 and #10) through a real MCP
  connection, not just a plan on paper.
- **Semantic search + LangGraph**: finds notes by meaning, not just exact
  words. Actually tested — searching "project deadline" correctly found a
  note about shipping a report by Friday, even though the word "deadline"
  was never in it, with a real similarity score to prove it.
- **Multi-user isolation**: every note is tagged with a user ID, and every
  part of the code filters by it. Actually tested with two separate users
  in two separate terminals, sharing the same database file — each one
  only ever saw their own notes.

See `DEMO.md` for all three, plus the main chat, working start to finish.

## A real problem we ran into (and how it's handled)

Free AI providers sometimes hit limits — too many requests too fast (rate
limits), or running out of the month's free usage (quota). Both happened
while testing this project against Hugging Face's free tier. The code
automatically retries on rate limits, but a used-up monthly quota can't be
fixed by waiting, so that one just shows a clear error and lets you try
again later or switch providers. This is explained more in `llm_providers.py`.


## Testing

To run the same 17 tests against a real AI model (Hugging Face, the
provider this was actually tested with):
```bash
set EVAL_LLM_PROVIDER=huggingface
python tests/eval_harness.py
```
(Windows PowerShell: use `$env:EVAL_LLM_PROVIDER = "huggingface"` instead
of `set`.) Worth knowing before running this: it makes 17+ real API calls
in a row, so it can hit Hugging Face's free monthly quota or rate limits
partway through — that happened during testing (see `DEMO.md`).

That's exactly why there's also a free, offline, fake-AI-model mode built
in — fast, free, and gives the same result every time, with no quota or
rate limit to worry about:
```bash
python tests/eval_harness.py
```
This is the default when no provider is set. Not a shortcut — real AI
providers have limits, so an automated test suite shouldn't depend on one
to run reliably every time.

For proof it also works with a real AI model without needing to run the
whole suite, see `DEMO.md` — real, unedited conversations, not test
scenarios.


## Not run yet

`Dockerfile` and `docker-compose.yml` are there and ready, but not run as
part of this. Everything else in `bonus/` — MCP + LangGraph, and semantic
search + LangGraph — is tested and working, shown in `DEMO.md`.


