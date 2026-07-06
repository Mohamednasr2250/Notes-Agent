

# Tool Schema Documentation

The agent has 7 tools that it can use. They are defined in notes_agent/tools.py inside TOOL_SCHEMAS, which are sent to the LLM as the available functions. The tools are executed by ToolExecutor in the same file. Every tool returns a JSON-serializable dictionary with at least an "ok": bool key, and an "error": str key if something goes wrong.

To use update_note or delete_note, the agent needs a specific note_id; it cannot use a keyword. Since there is no tool to update or delete a note by keyword, the note_id must first be obtained from search_notes or get_note. This makes the model ask the user which note they mean if more than one note matches, instead of guessing.


update_note and delete_note also do not have a confirmed parameter. Instead, agent.py checks these tool calls before they reach the executor. The tool is only executed after the user clearly confirms the action in a later message. See the README section **"How confirmation works"** for more details.





## 1- add_note

Purpose: Create a new note.


Parameters: 
- title: short title (its string and required).
- body:  have the content of the note (its string and required).
- tags: categories/tags, like ["maintenance"] (its array of string and optional).

Returns:


In normal return:
{"ok": true, "note": {"id": 1, "title": "...", "body": "...", "tags": [...], "created_at": "...", "updated_at": "..."}}

On failure like missing title or body return:
{"ok": false, "error": "Both a title and body are required to save a note."}






## 2- search_notes

Purpose: Search for notes using a keyword, tag, or date range. (it must be used before update_note or delete_note to get the correct note_id)

Parameters:

* query: keywords to search for in the note title, body, or tags using SQLite FTS5 (its string and optional).
* tag:  filter notes by an exact tag (its string and optional).
* date_from: show notes updated on or after this ISO date/datetime (its string and optional)..
* date_to:  show notes updated on or before this ISO date/datetime (its string and optional)..

*If no parameters are provided, the tool simply returns the most recent notes.



Returns:


{"ok": true, "count": 2, "notes": [{"id": 1, "title": "...", "snippet": "...", "tags": [...], "updated_at": "..."}, ...]}


## 3- get_note

Purpose: Fetch one note's full content by id.


Parameters:
- note_id: the note's id (its integer and required).


Returns:

In normal returns
{"ok": true, "note": {"id": 1, "title": "...", "body": "...", "tags": [...], "created_at": "...", "updated_at": "..."}}

On failure:
{"ok": false, "error": "No note with id 7."}







## 4- update_note

Purpose: Update the title, body, and/or tags of an existing note.


Parameters: 
- note_id: must come from search_notes/get_note (its integer and required).
- title: new title, if changing it (its string and optional).
- body: new body, if changing it  (its string and optional).
- tags: new tag list, if changing it (its array of string and optional).

Returns: (once actually applied, after confirmation)

{"ok": true, "note": {"id": 1, "title": "...", "body": "...", "tags": [...], "updated_at": "..."}}


*The previous title/body/tags are snapshotted into note_history before
being overwritten, enabling undo_last_action.




## 5- delete_note

Purpose: Delete a note by id. Soft delete — sets a deleted_at timestamp rather
than removing the row, so it's recoverable via undo_last_action.


Parameters:
- note_id: must come from search_notes/get_note (its integer and required).

Returns:

{"ok": true, "deleted_id": 1}







## 6- undo_last_action

Purpose: Reverse the single most recent mutation (add, update, or delete) tracked for this conversation. 

no parameters.

Returns

In normal return:

{"ok": true, "undone": "delete", "note_id": 1, "detail": "Restored note #1 (\"...\")."}


On failure (nothing to undo, or no history for an update revert) return:

{"ok": false, "error": "There's nothing to undo yet."}




## 7- list_recurring_issues

Purpose: Scan notes under a tag for keywords appearing in more than one note's body, a lightweight way to surface a recurring problem. 

Parameters: 
- tag: tag to scan; defaults to `"maintenance" (its string and optional).

Returns

{
  "ok": true,
  "tag": "maintenance",
  "notes_scanned": 3,
  "flagged": [{"keyword": "boiler", "note_ids": [1, 2]}]
}

