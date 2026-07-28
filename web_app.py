"""
Minimal web chat for the notes agent - one new file, doesn't touch
agent.py/tools.py/storage.py/cli.py at all.

Each browser gets its own Flask session cookie, and that session's id is
used directly as the user_id passed into Agent - so two different browsers
talking to the same running app automatically get isolated notes, for
free, because that isolation was already built into storage.py from the
start. No new auth code needed here.

Known limitation, stated plainly: agents are kept in an in-memory dict
(session_id -> Agent), not persisted or shared across processes. Fine for
a free single-instance host (Render's free tier runs one instance), but
would need a real session store (Redis, a DB-backed session) to survive a
restart or scale past one process. Notes themselves DO persist properly
(SQLite file), only the in-progress conversation state does not.

Run locally:
    pip install flask
    python web_app.py
Then open http://localhost:5000

Deploy free: see README.md's "Deploying this" section.
"""


import os
import uuid

from flask import Flask, request, jsonify, session, render_template_string

from notes_agent.storage import NotesStore
from notes_agent.agent import Agent
from notes_agent.llm_providers import get_provider
from notes_agent.cli import load_dotenv_simple

load_dotenv_simple()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

DB_PATH = os.environ.get("NOTES_DB_PATH", "notes.db")
PROVIDER_NAME = os.environ.get("LLM_PROVIDER", "mock")

_store = NotesStore(DB_PATH)
_agents = {}  # session_id -> Agent, see the in-memory limitation note above


def _get_agent() -> Agent:
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex
    sid = session["session_id"]
    if sid not in _agents:
        try:
            provider = get_provider(PROVIDER_NAME)
        except RuntimeError:
            provider = get_provider("mock")
        _agents[sid] = Agent(_store, user_id=sid, provider=provider)
    return _agents[sid]


PAGE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Notes Agent</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 40px auto; padding: 0 16px; }
    h1 { font-size: 1.2rem; color: #333; }
    #chat { border: 1px solid #ddd; border-radius: 8px; height: 60vh; overflow-y: auto; padding: 12px; margin-bottom: 12px; }
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
  <h1>Notes Agent</h1>
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
    _get_agent()  # ensures a session cookie is set on first load
    return render_template_string(PAGE)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify({"reply": "Say something and I'll help with your notes."})
    agent = _get_agent()
    try:
        reply = agent.send(text)
    except Exception as e:
        reply = f"Something went wrong on my end ({e}). Let's try that again."
    return jsonify({"reply": reply})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
