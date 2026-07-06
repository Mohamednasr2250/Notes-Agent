
# Terminal chat interface,to run it use: python -m notes_agent.cli
# for Env vars, see .env.example


import os
import sys

# allow `python -m notes_agent.cli` or `python notes_agent/cli.py`

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notes_agent.storage import NotesStore
from notes_agent.agent import Agent
from notes_agent.llm_providers import get_provider



# reads .env by hand instead of pulling in python-dotenv,keeps this stdlib-only


def load_dotenv_simple(path=".env"):

    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())




def main():
    load_dotenv_simple()
    db_path = os.environ.get("NOTES_DB_PATH", "notes.db")
    user_id = os.environ.get("USER_ID", "default_user")
    provider_name = os.environ.get("LLM_PROVIDER", "mock")

    store = NotesStore(db_path)
    try:
        provider = get_provider(provider_name)

    # missing/bad API key for the chosen provider, drop to mock instead

    except RuntimeError as e:

        print(f"[!] {e}\n falling back to the offline mock provider (heuristic,no real NLU).\n"
              f"    set LLM_PROVIDER and an API key in .env for real natural-lang understanding.\n")
        provider = get_provider("mock")

    agent = Agent(store, user_id=user_id, provider=provider)

    print("notes agent ready. (provider: %s, db: %s, user: %s)" % (provider_name, db_path, user_id))
    print("type 'exit' or 'quit' to leave.\n")


    # main chat loop

    while True:
        try:
            user_text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            break
        if not user_text:
            continue
        if user_text.lower() in ("exit", "quit"):
            print("bye.")
            break
        try:
            reply = agent.send(user_text)


        # keep the CLI alive instead of crashing the whole session

        except Exception as e:
            reply = f"there is something went wrong on my end ({e}). Let's try that again."
        print(f"agent> {reply}\n")




if __name__ == "__main__":
    main()
