"""
MCP and LangGraph example for the notes agent.

This file can run as:
- an MCP server that exposes the notes tools.
- a LangGraph client that connects to the server and uses those tools.
"""

import asyncio
import os
import sys


# Load environment variables from a .env file.

def _load_dotenv_simple(path=".env"):
  
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip()) 


_load_dotenv_simple()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notes_agent.storage import NotesStore
from notes_agent.tools import ToolExecutor



# Start the MCP server and expose the notes tools.


def run_server():
    from mcp.server.fastmcp import FastMCP

    db_path = os.environ.get("NOTES_DB_PATH", "notes.db")
    user_id = os.environ.get("USER_ID", "default_user")
    store = NotesStore(db_path)
    executor = ToolExecutor(store, user_id)

    mcp = FastMCP("notes-agent")

    @mcp.tool()
    def add_note(title: str, body: str, tags: list[str] = None) -> dict:
        """Create a new note with a title, body, and optional tags."""
        return executor.execute("add_note", {"title": title, "body": body, "tags": tags or []})

    @mcp.tool()
    def search_notes(query: str = "", tag: str = "", date_from: str = "", date_to: str = "") -> dict:
        """Search notes by keyword, tag, and/or date range."""
        return executor.execute("search_notes", {
            "query": query or None, "tag": tag or None,
            "date_from": date_from or None, "date_to": date_to or None,
        })

    @mcp.tool()
    def get_note(note_id: int) -> dict:
        """Fetch a single note by id."""
        return executor.execute("get_note", {"note_id": note_id})

    @mcp.tool()
    def update_note(note_id: int, title: str = "", body: str = "", tags: list[str] = None) -> dict:
        """Update a note's title, body, and/or tags."""
        args = {"note_id": note_id}
        if title:
            args["title"] = title
        if body:
            args["body"] = body
        if tags is not None:
            args["tags"] = tags
        return executor.execute("update_note", args)

    @mcp.tool()
    def delete_note(note_id: int) -> dict:
        """Delete a note (soft delete - recoverable via undo_last_action)."""
        return executor.execute("delete_note", {"note_id": note_id})

    @mcp.tool()
    def undo_last_action() -> dict:
        """Reverse the most recent add/update/delete."""
        return executor.execute("undo_last_action", {})

    @mcp.tool()
    def list_recurring_issues(tag: str = "maintenance") -> dict:
        """Flag keywords recurring across notes under a tag."""
        return executor.execute("list_recurring_issues", {"tag": tag})

    mcp.run(transport="stdio")

# Start a LangGraph agent and connect to the MCP server.


async def run_client():
    from langgraph.prebuilt import create_react_agent
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_openai import ChatOpenAI


# Launch this file as an MCP server and connect to it.



    client = MultiServerMCPClient({
        "notes": {
            "command": sys.executable,
            "args": [os.path.abspath(__file__), "--serve"],
            "transport": "stdio",
        }
    })
    tools = await client.get_tools()


# Create the language model used by the agent.


    llm = ChatOpenAI(
        model=os.environ.get("HF_MODEL", "openai/gpt-oss-120b:together"),
        api_key=os.environ.get("HF_TOKEN"),
        base_url="https://router.huggingface.co/v1",
    )


    # Build the LangGraph ReAct agent.


    
    agent = create_react_agent(llm, tools)

    result = await agent.ainvoke({
        "messages": [{
            "role": "user",
            "content": "Save a note about a leaking radiator in Flat 6, tag it as maintenance",
        }]
    })

    from notes_agent.llm_providers import _clean_harmony_leakage
    print(_clean_harmony_leakage(result["messages"][-1].content))


if __name__ == "__main__":
    if "--serve" in sys.argv:
        run_server()
    else:
        asyncio.run(run_client())
