
"""
SQLite storage for notes, Soft delete and a history table so undo works.
"""

import sqlite3
import json
import datetime
from dataclasses import dataclass
from typing import Optional, List

#note object

@dataclass
class Note:
    id: int
    title: str
    body: str
    tags: List[str]
    created_at: str
    updated_at: str
    user_id: str = "default_user"
    deleted_at: Optional[str] = None

    def to_dict(self):
        return {
            "id": self.id,"title": self.title,"body": self.body,
            "tags": self.tags,"created_at": self.created_at,"updated_at": self.updated_at,
        }

    def snippet(self, n=140):
        b = self.body.replace("\n", " ")
        return b if len(b) <= n else b[:n].rstrip() + "..."



#manage all note db ops

class NotesStore:
    def __init__(self, db_path: str = "notes.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute(

            # deleted_at stays NULL for live notes — delete_note() just sets it instead of removing the row, so undo can bring it back
            
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,user_id TEXT NOT NULL DEFAULT 'default_user',
                title TEXT NOT NULL,body TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,deleted_at TEXT
            )
            """
        )
        cur.execute(

            # one row per edit, written right before update_note() overwrites the note, so an update can be reverted later

            """
            CREATE TABLE IF NOT EXISTS note_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,note_id INTEGER NOT NULL,
                title TEXT NOT NULL,body TEXT NOT NULL,
                tags TEXT NOT NULL,snapshot_at TEXT NOT NULL
            )
            """
        )
        cur.execute(

            # FTS5 index for keyword search, kept in sync via the triggers below

            """
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                title, body, tags, content='notes', content_rowid='id'
            )
            """
        )

        # mirrors every insert/update/delete on notes into notes_fts automatically

        cur.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
                INSERT INTO notes_fts(rowid, title, body, tags)
                VALUES (new.id, new.title, new.body, new.tags);
            END;
            CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, title, body, tags)
                VALUES('delete', old.id, old.title, old.body, old.tags);
            END;
            CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
                INSERT INTO notes_fts(notes_fts, rowid, title, body, tags)
                VALUES('delete', old.id, old.title, old.body, old.tags);
                INSERT INTO notes_fts(rowid, title, body, tags)
                VALUES (new.id, new.title, new.body, new.tags);
            END;
            """
        )
        self.conn.commit()

    @staticmethod
    def _now():
        return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    def _row_to_note(self, row) -> Note:
        return Note(
            id=row["id"], title=row["title"], body=row["body"],
            tags=json.loads(row["tags"]), created_at=row["created_at"],
            updated_at=row["updated_at"], user_id=row["user_id"],
            deleted_at=row["deleted_at"],
        )










    # CRUD






    # insert a new note and return the freshly created row

    def add_note(self, title: str, body: str, tags: Optional[List[str]] = None,
                 user_id: str = "default_user") -> Note:
        tags = tags or []
        now = self._now()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO notes (user_id, title, body, tags, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, title, body, json.dumps(tags), now, now),
        )
        self.conn.commit()
        return self.get_note(cur.lastrowid, user_id)





    # fetch one note by id, excluding soft-deleted ones unless asked

    def get_note(self, note_id: int, user_id: str = "default_user",
                 include_deleted: bool = False) -> Optional[Note]:
        q = "SELECT * FROM notes WHERE id = ? AND user_id = ?"
        if not include_deleted:
            q += " AND deleted_at IS NULL"
        cur = self.conn.execute(q, (note_id, user_id))
        row = cur.fetchone()
        return self._row_to_note(row) if row else None




    # store the note's current state before it gets overwritten

    def _snapshot_history(self, note: Note):
        self.conn.execute(
            "INSERT INTO note_history (note_id, title, body, tags, snapshot_at) VALUES (?, ?, ?, ?, ?)",
            (note.id, note.title, note.body, json.dumps(note.tags), self._now()),
        )
  



    # apply only the fields that were actually passed, keep the rest unchanged

    def update_note(self, note_id: int, title: Optional[str] = None,
                     body: Optional[str] = None, tags: Optional[List[str]] = None,
                     user_id: str = "default_user") -> Optional[Note]:
        note = self.get_note(note_id, user_id)
        if not note:
            return None
        self._snapshot_history(note)  # save pre-change state for undo
        new_title = title if title is not None else note.title
        new_body = body if body is not None else note.body
        new_tags = tags if tags is not None else note.tags
        self.conn.execute(
            "UPDATE notes SET title=?, body=?, tags=?, updated_at=? WHERE id=? AND user_id=?",
            (new_title, new_body, json.dumps(new_tags), self._now(), note_id, user_id),
        )
        self.conn.commit()
        return self.get_note(note_id, user_id)
    




    # grab and remove the last saved snapshot for a note, used by undo


    def pop_last_history(self, note_id: int) -> Optional[dict]:
        """Remove and return the most recent pre-change snapshot for a note
        (used by undo). Returns None if there's no history for this note."""
        cur = self.conn.execute(
            "SELECT * FROM note_history WHERE note_id=? ORDER BY id DESC LIMIT 1", (note_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        self.conn.execute("DELETE FROM note_history WHERE id=?", (row["id"],))
        self.conn.commit()
        return {"title": row["title"], "body": row["body"], "tags": json.loads(row["tags"])}






    # soft delete — just flips deleted_at instead of dropping the row

    def delete_note(self, note_id: int, user_id: str = "default_user") -> bool:
        """Soft delete — marks deleted_at, doesn't remove the row."""
        note = self.get_note(note_id, user_id)
        if not note:
            return False
        self.conn.execute(
            "UPDATE notes SET deleted_at=? WHERE id=? AND user_id=?",
            (self._now(), note_id, user_id),
        )
        self.conn.commit()
        return True
  




    # actually removes the row, only used to undo an add  

    def hard_delete_note(self, note_id: int, user_id: str = "default_user") -> bool:
        """Permanently remove a row (used to undo an add_note, not for user-facing delete)."""
        note = self.get_note(note_id, user_id, include_deleted=True)
        if not note:
            return False
        self.conn.execute("DELETE FROM notes WHERE id=? AND user_id=?", (note_id, user_id))
        self.conn.commit()
        return True
   



    # clears deleted_at, brings a soft-deleted note back


    def restore_note(self, note_id: int, user_id: str = "default_user") -> Optional[Note]:
        self.conn.execute(
            "UPDATE notes SET deleted_at=NULL WHERE id=? AND user_id=?", (note_id, user_id)
        )
        self.conn.commit()
        return self.get_note(note_id, user_id)







    #  Search/list 


    # plain filtered listing — no keyword search, just tag/date filters


    def list_notes(self, user_id: str = "default_user", tag: Optional[str] = None,
                   date_from: Optional[str] = None, date_to: Optional[str] = None,
                   limit: int = 50) -> List[Note]:
        q = "SELECT * FROM notes WHERE user_id = ? AND deleted_at IS NULL"
        params: list = [user_id]
        if tag:
            q += " AND tags LIKE ?"
            params.append(f'%"{tag}"%')
        if date_from:
            q += " AND updated_at >= ?"
            params.append(date_from)
        if date_to:
            q += " AND updated_at <= ?"
            params.append(date_to)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        cur = self.conn.execute(q, params)
        return [self._row_to_note(r) for r in cur.fetchall()]





    # keyword search via FTS5, falls back to list_notes if no query given


    def search_notes(self, query: Optional[str] = None, tag: Optional[str] = None,
                      date_from: Optional[str] = None, date_to: Optional[str] = None,
                      user_id: str = "default_user", limit: int = 20) -> List[Note]:
        if not query:
            return self.list_notes(user_id, tag, date_from, date_to, limit)

        terms = " ".join(f'"{t}"*' for t in query.split() if t.strip())
        try:
            cur = self.conn.execute(
                """
                SELECT notes.* FROM notes
                JOIN notes_fts ON notes.id = notes_fts.rowid
                WHERE notes_fts MATCH ? AND notes.user_id = ? AND notes.deleted_at IS NULL
                ORDER BY rank LIMIT ?
                """,
                (terms, user_id, limit * 3),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            rows = []

        notes = [self._row_to_note(r) for r in rows]
        if tag:
            notes = [n for n in notes if tag.lower() in [t.lower() for t in n.tags]]
        if date_from:
            notes = [n for n in notes if n.updated_at >= date_from]
        if date_to:
            notes = [n for n in notes if n.updated_at <= date_to]
        return notes[:limit]




    # everything for a user, no limit — used by list_recurring_issues

    def all_notes(self, user_id: str = "default_user") -> List[Note]:
        return self.list_notes(user_id, limit=10_000)
