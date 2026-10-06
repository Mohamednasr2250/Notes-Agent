"""
Minimal web chat for the notes agent - one new file, doesn't touch
agent.py/tools.py/storage.py/cli.py at all.

User isolation: a visible username step. You type a name on the login
screen, it gets sanitized into a user_id, and that user_id is what gets
passed into Agent / NotesStore, so different names see different notes.
A session cookie remembers the name between page loads on the same
browser, but the isolation itself is the username, not the cookie - if
you log in as the same name from a different browser/device, you get
the same notes back.

Known limitation, stated plainly: agents are kept in an in-memory dict
(user_id -> Agent), not persisted or shared across processes. Fine for
a free single-instance host, but would need a real session store to
survive a restart or scale past one process. Notes themselves DO persist
properly (SQLite file on disk), only the in-progress conversation state
(recent note ids for follow-ups, pending confirmations) does not survive
a restart.

Run locally:
    pip install flask
    python web_app.py
Then open http://localhost:5000

Deploy free: see README.md's "Deploying this" section.
"""

import os
import re

from flask import Flask, request, jsonify, session, render_template_string, redirect, url_for

from notes_agent.storage import NotesStore
from notes_agent.agent import Agent
from notes_agent.llm_providers import get_provider
from notes_agent.cli import load_dotenv_simple

load_dotenv_simple()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Resolve the DB path relative to this file, not the process's current
# working directory - PythonAnywhere's WSGI runner can have a different
# cwd than where this file actually lives, which would otherwise create
# (or look for) notes.db in the wrong place.
_raw_db_path = os.environ.get("NOTES_DB_PATH", "notes.db")
DB_PATH = (
    _raw_db_path
    if os.path.isabs(_raw_db_path)
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), _raw_db_path)
)
PROVIDER_NAME = os.environ.get("LLM_PROVIDER", "mock")

_store = NotesStore(DB_PATH)
_agents = {}  # user_id -> Agent, see the in-memory limitation note above


def _sanitize_username(name: str) -> str:
    name = (name or "").strip().lower()
    name = re.sub(r"[^a-z0-9_\-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:40] or "guest"


def _get_agent(user_id: str) -> Agent:
    if user_id not in _agents:
        try:
            provider = get_provider(PROVIDER_NAME)
        except RuntimeError:
            provider = get_provider("mock")
        _agents[user_id] = Agent(_store, user_id=user_id, provider=provider)
    return _agents[user_id]


LOGIN_PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Notes Agent - sign in</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 420px; margin: 80px auto; padding: 0 16px; color: #222; }
    h1 { font-size: 1.3rem; }
    p.sub { color: #666; font-size: 0.92rem; line-height: 1.4; }
    form { display: flex; gap: 8px; margin-top: 20px; }
    input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }
    button { padding: 10px 16px; border: none; border-radius: 6px; background: #1a73e8; color: white;
             cursor: pointer; font-size: 1rem; }
  </style>
</head>
<body>
  <h1>Notes Agent</h1>
  <p class="sub">
    Pick a name. It's not a password - it's just how the app tells your notes apart
    from anyone else's using this link. Log in with the same name later and your
    notes will still be there; a different name starts a fresh, empty set of notes.
  </p>
  <form method="post" action="/login">
    <input name="username" autocomplete="off" placeholder="e.g. mohamed" autofocus required />
    <button type="submit">Start</button>
  </form>
</body>
</html>
"""

PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Notes Agent</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 680px; margin: 30px auto; padding: 0 16px; }
    h1 { font-size: 1.2rem; color: #333; display: flex; justify-content: space-between; align-items: center; }
    h1 .who { font-size: 0.85rem; color: #888; font-weight: normal; }
    h1 .who a { color: #1a73e8; text-decoration: none; margin-left: 8px; }
    details { border: 1px solid #ddd; border-radius: 8px; padding: 10px 14px; margin-bottom: 14px; background: #fafafa; }
    summary { cursor: pointer; font-weight: 600; font-size: 0.95rem; }
    details p, details ul { font-size: 0.88rem; color: #444; line-height: 1.5; }
    details code { background: #eee; padding: 1px 5px; border-radius: 4px; }
    #chat { border: 1px solid #ddd; border-radius: 8px; height: 55vh; overflow-y: auto; padding: 12px; margin-bottom: 12px; }
    .msg { margin: 8px 0; padding: 8px 12px; border-radius: 8px; max-width: 80%; white-space: pre-wrap; }
    .you { background: #e8f0fe; margin-left: auto; text-align: right; }
    .agent { background: #f1f1f1; }
    form { display: flex; gap: 8px; }
    input { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 6px; }
    button { padding: 10px 16px; border: none; border-radius: 6px; background: #1a73e8; color: white; cursor: pointer; }
    button:disabled { opacity: 0.5; }
  </style>
</head>
<body>
  <h1>Notes Agent <span class="who">signed in as {{ username }} <a href="/logout">switch user</a></span></h1>

  <details {{ "open" if mock else "" }}>
    <summary>How to talk to it{{ " (mock mode - rule-based, not a real AI model)" if mock else "" }}</summary>
    <p>
      {% if mock %}
      This deployment is running the free <strong>mock</strong> provider: a rule-based stand-in that
      recognizes a fixed set of phrasings below, not a real language model. Swap in a real provider
      (Hugging Face / Azure OpenAI) via the <code>LLM_PROVIDER</code> env var for open-ended understanding.
      {% else %}
      This deployment is running a real LLM provider, so phrasing is flexible - but here are some
      patterns that are guaranteed to work.
      {% endif %}
    </p>
    <ul>
      <li><strong>Add a note:</strong> <code>save a note about the boiler leak, tag it as maintenance</code></li>
      <li><strong>Search:</strong> <code>what did I write about the boiler?</code> or <code>find notes about rent</code></li>
      <li><strong>List by tag:</strong> <code>list notes tagged maintenance</code></li>
      <li><strong>Update:</strong> <code>update my note about the boiler to say it's fixed now</code></li>
      <li><strong>Delete:</strong> <code>delete the note about the boiler</code> (it will ask you to confirm first - reply <code>yes</code>)</li>
      <li><strong>Undo:</strong> <code>undo</code> (restores the last delete, or reverts the last update/add)</li>
      <li><strong>Follow-up on the last note:</strong> <code>add a deadline to that: by Friday</code></li>
      <li><strong>Recurring issues:</strong> <code>check for recurring issues tagged maintenance</code></li>
      <li><strong>Summarize:</strong> <code>summarize notes tagged maintenance</code></li>
    </ul>
  </details>

  <div id="chat"></div>
  <form id="form">
    <input id="input" autocomplete="off" placeholder="Save a note about..." />
    <button type="submit">Send</button>
  </form>
  <script>
    const chat = document.getElementById('chat');
    const form = document.getElementById('form');
    const input = document.getElementById('input');

    function addMsg(text, cls) {
      const div = document.createElement('div');
      div.className = 'msg ' + cls;
      div.textContent = text;
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      addMsg(text, 'you');
      input.value = '';
      input.disabled = true;
      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({message: text})
        });
        if (res.status === 401) { window.location.href = '/'; return; }
        const data = await res.json();
        addMsg(data.reply, 'agent');
      } catch (err) {
        addMsg('Something went wrong reaching the server.', 'agent');
      }
      input.disabled = false;
      input.focus();
    });
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    user_id = session.get("user_id")
    if not user_id:
        return render_template_string(LOGIN_PAGE)
    return render_template_string(
        PAGE, username=session.get("username", user_id), mock=(PROVIDER_NAME == "mock")
    )


@app.route("/login", methods=["POST"])
def login():
    raw = request.form.get("username", "")
    user_id = _sanitize_username(raw)
    session["user_id"] = user_id
    session["username"] = raw.strip() or user_id
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/chat", methods=["POST"])
def chat():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"reply": "Please sign in first."}), 401
    data = request.get_json(force=True) or {}
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify({"reply": "Say something and I'll help with your notes."})
    agent = _get_agent(user_id)
    try:
        reply = agent.send(text)
    except Exception as e:
        reply = f"Something went wrong on my end ({e}). Let's try that again."
    return jsonify({"reply": reply})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
