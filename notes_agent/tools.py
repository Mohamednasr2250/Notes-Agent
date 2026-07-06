
#Tool schemas (sent to the LLM) and the executor that runs them.
#No delete/update-by-keyword tool on purpose — note_id has to come from
#search_notes/get_note first, so the model can't guess which note to touch.
#Confirmation gating for update_note/delete_note lives in agent.py, not here.


import re
from collections import defaultdict
from typing import Optional, List, Dict, Any
from .storage import NotesStore, Note

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "have", "has", "had",
    "was", "were", "will", "would", "could", "should", "about", "from",
    "into", "again", "still", "note", "notes", "tenant", "flat",
}


TOOL_SCHEMAS = [
    {
        "name": "add_note",
        "description": (
            "Create a new note with a title, body text, and optional tags. "
            "Use this whenever the user asks to save/add/create/jot down a note."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short descriptive title for the note."},
                "body": {"type": "string", "description": "The main content of the note."},
                "tags": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Optional list of tags/categories, e.g. ['maintenance'].",
                },
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "search_notes",
        "description": (
            "Search existing notes by keyword, tag, and/or date range. Always use this "
            "BEFORE update_note or delete_note to resolve which note(s) the user means. "
            "If it returns more than one note and the user's request was about a single "
            "note, you must ask the user which one they mean instead of guessing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text keywords to search title/body/tags."},
                "tag": {"type": "string", "description": "Exact tag to filter by."},
                "date_from": {"type": "string", "description": "ISO date/datetime lower bound on last-updated."},
                "date_to": {"type": "string", "description": "ISO date/datetime upper bound on last-updated."},
            },
            "required": [],
        },
    },
    {
        "name": "get_note",
        "description": "Fetch the full content of a single note by its exact id.",
        "input_schema": {
            "type": "object",
            "properties": {"note_id": {"type": "integer"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "update_note",
        "description": (
            "Update the title, body, and/or tags of an existing note, identified by note_id "
            "(get the id from search_notes/get_note first — never guess an id). This is a "
            "significant change to saved content: preview it for the user and get their "
            "explicit agreement before you actually call this (the system will ask them to "
            "confirm on your behalf and only forward the call once they say yes)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "integer"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "delete_note",
        "description": (
            "Delete a note by note_id (get the id from search_notes/get_note first). "
            "This is destructive: the system will ask the user to confirm before actually "
            "applying it. Deletions are soft (recoverable via undo_last_action)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"note_id": {"type": "integer"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "undo_last_action",
        "description": (
            "Reverse the single most recent note mutation (an add, update, or delete) for "
            "this conversation. Use when the user says 'undo', 'undo that', or similar."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_recurring_issues",
        "description": (
            "Scan notes under a tag (default 'maintenance') for keywords that appear in "
            "more than one note's body — a lightweight way to flag a recurring problem "
            "(e.g. 'boiler' showing up across three separate repair notes) before it "
            "becomes urgent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"tag": {"type": "string", "description": "Tag to scan, default 'maintenance'."}},
            "required": [],
        },
    },
]


def _note_summary(n: Note) -> Dict[str, Any]:
    return {"id": n.id, "title": n.title, "snippet": n.snippet(), "tags": n.tags, "updated_at": n.updated_at}


class ToolExecutor:

    # recent_note_ids: last 5 referenced notes, newest first — lets "that
    # note" / "the last one" resolve without re-searching.
    # last_mutation: the one most recent add/update/delete, for undo.



    # store, user_id, and the two bits of session state above start empty

    def __init__(self, store: NotesStore, user_id: str = "default_user"):
        self.store = store
        self.user_id = user_id
        self.recent_note_ids: List[int] = []
        self.last_mutation: Optional[Dict[str, Any]] = None


    # most recently touched note, or None if nothing's happened yet this session

    @property
    def last_note_id(self) -> Optional[int]:
        return self.recent_note_ids[0] if self.recent_note_ids else None
    

    # bumps a note to the front of recent_note_ids, capped at 5

    def _touch(self, note_id: int):
        if note_id in self.recent_note_ids:
            self.recent_note_ids.remove(note_id)
        self.recent_note_ids.insert(0, note_id)
        self.recent_note_ids = self.recent_note_ids[:5]



    # dispatches a tool call by name to its _tool_* handler, catching any exception

    def execute(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"ok": False, "error": f"Unknown tool '{name}'"}
        try:
            return handler(args or {})
        except Exception as e:
            return {"ok": False, "error": f"Tool '{name}' failed: {e}"}
        

    # requires both title and body — refuses to save an empty/vague note


    def _tool_add_note(self, args):
        title = (args.get("title") or "").strip()
        body = (args.get("body") or "").strip()
        if not title or not body:
            return {"ok": False, "error": "Both a title and body are required to save a note."}
        note = self.store.add_note(title, body, args.get("tags") or [], self.user_id)
        self._touch(note.id)
        self.last_mutation = {"type": "add", "note_id": note.id}
        return {"ok": True, "note": note.to_dict()}
    
    
    # only tracks the note if search narrowed it down to exactly one match

    def _tool_search_notes(self, args):
        notes = self.store.search_notes(
            query=args.get("query"), tag=args.get("tag"),
            date_from=args.get("date_from"), date_to=args.get("date_to"),
            user_id=self.user_id,
        )
        if len(notes) == 1:
            self._touch(notes[0].id)
        return {"ok": True, "count": len(notes), "notes": [_note_summary(n) for n in notes]}
    

    # fetch one note by exact id, used to resolve a note before update/delete
    
    def _tool_get_note(self, args):
        note = self.store.get_note(args["note_id"], self.user_id)
        if not note:
            return {"ok": False, "error": f"No note with id {args.get('note_id')}."}
        self._touch(note.id)
        return {"ok": True, "note": note.to_dict()}


    # only overwrites the fields that were actually passed in
  
    def _tool_update_note(self, args):
        note_id = args.get("note_id")
        existing = self.store.get_note(note_id, self.user_id)
        if not existing:
            return {"ok": False, "error": f"No note with id {note_id}. It may not exist or was deleted."}
        updated = self.store.update_note(
            note_id, title=args.get("title"), body=args.get("body"),
            tags=args.get("tags"), user_id=self.user_id,
        )
        self._touch(updated.id)
        self.last_mutation = {"type": "update", "note_id": updated.id}
        return {"ok": True, "note": updated.to_dict()}
    




    # also drops the note from recent_note_ids since it's gone now

    def _tool_delete_note(self, args):
        note_id = args.get("note_id")
        existing = self.store.get_note(note_id, self.user_id)
        if not existing:
            return {"ok": False, "error": f"No note with id {note_id}. It may already be deleted."}
        self.store.delete_note(note_id, self.user_id)
        if note_id in self.recent_note_ids:
            self.recent_note_ids.remove(note_id)
        self.last_mutation = {"type": "delete", "note_id": note_id}
        return {"ok": True, "deleted_id": note_id}
    




    # reverses whichever of add/update/delete happened most recently

    def _tool_undo_last_action(self, args):
        m = self.last_mutation
        if not m:
            return {"ok": False, "error": "There's nothing to undo yet."}
        note_id = m["note_id"]
        if m["type"] == "add":
            self.store.hard_delete_note(note_id, self.user_id)
            result = {"ok": True, "undone": "add", "note_id": note_id,
                      "detail": f"Removed note #{note_id} that was just added."}
        elif m["type"] == "delete":
            restored = self.store.restore_note(note_id, self.user_id)
            result = {"ok": True, "undone": "delete", "note_id": note_id,
                      "detail": f"Restored note #{note_id} (\"{restored.title}\")." if restored else "Restore failed."}
        elif m["type"] == "update":
            prev = self.store.pop_last_history(note_id)
            if not prev:
                return {"ok": False, "error": "No prior version found to revert to."}
            reverted = self.store.update_note(note_id, title=prev["title"], body=prev["body"],
                                               tags=prev["tags"], user_id=self.user_id)
            



            # updating again writes a NEW history row we don't want to keep growing forever

            # pop it so a second undo doesn't just re-apply the same revert pointlessly

            self.store.pop_last_history(note_id)
            result = {"ok": True, "undone": "update", "note_id": note_id,
                      "detail": f"Reverted note #{note_id} to its previous content."}
        else:
            return {"ok": False, "error": "Unrecognized last action."}
        self.last_mutation = None
        return result




    # flags any keyword (4+ letters, stopwords excluded) showing up in more than one note


    def _tool_list_recurring_issues(self, args):
        tag = args.get("tag") or "maintenance"
        notes = self.store.list_notes(user_id=self.user_id, tag=tag, limit=200)
        word_to_notes: Dict[str, set] = defaultdict(set)
        for n in notes:
            words = set(re.findall(r"[a-zA-Z]{4,}", n.body.lower()))
            for w in words - _STOPWORDS:
                word_to_notes[w].add(n.id)
        flagged = [
            {"keyword": w, "note_ids": sorted(ids)}
            for w, ids in word_to_notes.items() if len(ids) >= 2
        ]
        flagged.sort(key=lambda f: -len(f["note_ids"]))
        return {"ok": True, "tag": tag, "notes_scanned": len(notes), "flagged": flagged}
