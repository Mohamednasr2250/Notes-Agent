

# The conversation loop.
# agent.py handles confirmation for update_note and delete_note.
# It waits for the user's confirmation before calling executor.execute().

from __future__ import annotations
import re
from typing import List, Optional
from .tools import TOOL_SCHEMAS, ToolExecutor
from .storage import NotesStore
from .llm_providers import LLMProvider, get_provider


SYSTEM_PROMPT = """You are a notes assistant for tenant/property management use cases \
(repairs, maintenance, tenancy renewals, inspections, tenant queries) as well as general \
personal notes. You help the user add, search, update, delete, and reason about their \
notes using the provided tools ONLY (never invent note content or ids from memory).

Rules you must follow:
1. To update or delete a note, you must first resolve it to a concrete note_id via \
search_notes (or get_note if you already have the id from context). NEVER guess an id.
2. If search_notes returns more than one plausible match for an update/delete request, \
list the candidates (id, title, short snippet) and ask the user which one they mean. \
Do not act until they clarify.
3. update_note and delete_note are destructive. When you call one, the tool result will \
tell you it's only a preview and that the system will separately confirm with the user — \
your job is just to clearly describe what will change and ask them to confirm in plain \
language. Never say a note was updated/deleted unless a later tool result actually \
confirms it happened.
4. If a search returns no results, say so plainly and suggest a concrete alternative \
(different keywords, a tag, or listing recent notes) — never pretend something was found.
5. The user may refer back to a recently discussed note with words like "that note", \
"it", or "the last one". Session context below lists recently referenced notes, most \
recent first — use get_note on the right one rather than re-searching when that's clearly \
what they mean.
6. If the user says "undo" or similar, call undo_last_action.
7. Be concise and conversational. Confirm actions in plain language, not JSON.
8. To add a note you need at least a title and body; if the user's message is too vague \
to extract real content, ask them what they'd like the note to say rather than saving an \
empty note.

Session context: {context}
"""




# wires up storage,provider,and the tool executor for one user session

class Agent:
    def __init__(self, store: NotesStore, user_id: str = "default_user",
                 provider: Optional[LLMProvider] = None):
        self.store = store
        self.user_id = user_id
        self.provider = provider or get_provider()
        self.executor = ToolExecutor(store, user_id)
        self.history: List[dict] = []
        self.max_tool_hops = 6
        self.pending_action: Optional[dict] = None  # {"name", "args", "question"}



    # builds the system prompt fresh each turn,injecting recently touched notes

    def _system_prompt(self) -> str:
        ids = self.executor.recent_note_ids
        if ids:
            parts = []
            for nid in ids:
                n = self.store.get_note(nid, self.user_id)
                if n:
                    parts.append(f'#{nid} ("{n.title}")')
            ctx = "recently referenced notes, most recent first: " + ", ".join(parts) if parts else "none yet"
        else:
            ctx = "none yet"
        return SYSTEM_PROMPT.format(context=ctx)
    


    # some providers return a list of tool-result messages, some return one, normalize both

    def _append_tool_results_message(self, tool_results):
        msg = self.provider.build_tool_results_message(tool_results)
        if isinstance(msg, list):
            self.history.extend(msg)
        else:
            self.history.append(msg)



    # looks up the note and drafts the yes or no question before anything gets touched

    def _build_preview(self, name: str, args: dict) -> Optional[dict]:
        """Returns {'question': str, 'summary': dict} for a destructive call,
        or None if the target note doesn't exist (caller should surface an error instead)."""
        note_id = args.get("note_id")
        existing = self.store.get_note(note_id, self.user_id)
        if not existing:
            return None
        if name == "delete_note":
            question = f'Delete note #{note_id} ("{existing.title}")? You can undo this after. (yes/no)'
            summary = {"note_id": note_id, "title": existing.title, "snippet": existing.snippet()}
        else:  # update_note
            changes = {k: v for k, v in {
                "title": args.get("title"), "body": args.get("body"), "tags": args.get("tags"),
            }.items() if v is not None}
            question = f"I'll update note #{note_id} with {changes} — go ahead? (yes/no)"
            summary = {"note_id": note_id, "current_title": existing.title,
                       "current_body": existing.body, "proposed_changes": changes}
        return {"question": question, "summary": summary}
    



    # turns a tool's raw output into the line the user actually sees

    def _describe_result(self, name: str, output: dict) -> str:
        if not output.get("ok"):
            return f"That didn't work: {output.get('error', 'unknown error')}"
        if name == "delete_note":
            return f"Done — deleted note #{output['deleted_id']}. Say 'undo' if that was a mistake."
        if name == "update_note":
            n = output["note"]
            return f'Done — updated note #{n["id"]}: "{n["title"]}".'
        return "Done."




    # main turn loop: checks for a pending yes/no first, otherwise lets the
    # model call tools until it gives a final answer or hits max_tool_hops


    def send(self, user_text: str) -> str:
        #Resolve a pending confirmation entirely in code, before the
        # LLM ever sees this turn.


        if self.pending_action is not None:
            low = user_text.lower()
            pending = self.pending_action


            # treat this reply as a yes — actually run the pending action now

            if re.search(r"\b(yes|yep|confirm|go ahead|do it|sure|correct)\b", low):
                self.pending_action = None
                output = self.executor.execute(pending["name"], pending["args"])
                reply = self._describe_result(pending["name"], output)

            # treat this reply as a no — drop the pending action, nothing gets touched

            elif re.search(r"\b(no|don't|cancel|stop|nevermind|never mind)\b", low):
                self.pending_action = None
                reply = "Okay, I won't do that. Nothing was changed."
            else:
                reply = f"Just to be clear — {pending['question']}"
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": reply})
            return reply

        self.history.append({"role": "user", "content": user_text})

        # MockProvider tracks the last-touched note itself for follow-up references

        if hasattr(self.provider, "_last_note_id"):
            self.provider._last_note_id = self.executor.last_note_id


        # let the model call tools back-to-back until it gives a final answer or hits the cap
        hops = 0
        while hops < self.max_tool_hops:
            hops += 1
            result = self.provider.send(self.history, TOOL_SCHEMAS, self._system_prompt())
            msg = result.raw_assistant_message
            self.history.extend(msg) if isinstance(msg, list) else self.history.append(msg)

            if not result.tool_calls:
                return result.text or ""

            tool_outputs = []
            for tc in result.tool_calls:


                # destructive calls get intercepted here instead of running immediately

                if tc.name in ("delete_note", "update_note") and self.pending_action is None:
                    preview = self._build_preview(tc.name, tc.input)
                    if preview is None:
                        output = {"ok": False, "error": f"No note with id {tc.input.get('note_id')}."}
                    else:
                        self.pending_action = {"name": tc.name, "args": tc.input, "question": preview["question"]}
                        output = {"ok": True, "needs_confirmation": True,
                                  "question": preview["question"], **preview["summary"]}
                else:
                    output = self.executor.execute(tc.name, tc.input)
                tool_outputs.append({"id": tc.id, "output": output})
            self._append_tool_results_message(tool_outputs)


        # hit max_tool_hops without a final answer — ask the user to simplify instead of looping forever


        return ("I'm having trouble completing that in one go — could you rephrase "
                "or break the request into smaller steps?")
