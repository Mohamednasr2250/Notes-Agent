"""
LLM provider implementations for the notes agent.

This file provides a common interface for different LLM providers
(Azure OpenAI, Hugging Face, and Mock) so the rest of the project
can use any provider without changing the agent logic.
"""

from __future__ import annotations
import os
import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional




# bwahadhom ll agent

@dataclass
class ToolCall:            #info el tool
    id: str
    name: str
    input: Dict[str, Any]


@dataclass
class TurnResult:      # rad el llm
    text: Optional[str]
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw_assistant_message: Any = None


#btaked enohom mawgoden

class LLMProvider:
    def send(self, messages: List[dict], tools: List[dict], system: str) -> TurnResult:
        raise NotImplementedError

    def build_tool_results_message(self, results: List[Dict[str, Any]]) -> Any:
        raise NotImplementedError





# Convert tool schemas to the OpenAI tool format.

def _to_openai_tools(tools):
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"], "parameters": t["input_schema"],
    }} for t in tools]



#####################



# Remove Harmony channel names (analysis, commentary, final)
# if they appear in the model's response.
_HARMONY_CHANNEL_LEAK_RE = re.compile(r"^(?:analysis|commentary|final)(?=[A-Z])")

# Remove leaked Harmony special tokens from the response.
_HARMONY_TOKEN_RE = re.compile(r"<\|(?:start|end|message|channel|return|call)\|>[a-zA-Z]*")



# Clean unwanted Harmony text from the model response.

def _clean_harmony_leakage(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    cleaned = _HARMONY_TOKEN_RE.sub("", text)
    cleaned = _HARMONY_CHANNEL_LEAK_RE.sub("", cleaned)
    return cleaned.strip() or text



# Parse the OpenAI response and extract text and tool calls.
def _parse_openai_response(data) -> TurnResult:
    msg = data["choices"][0]["message"]
    tool_calls = [
        ToolCall(id=tc["id"], name=tc["function"]["name"],
                 input=json.loads(tc["function"]["arguments"] or "{}"))
        for tc in (msg.get("tool_calls") or [])
    ]
    cleaned_text = _clean_harmony_leakage(msg.get("content"))


# Keep only the required fields before saving the assistant message.

    clean_msg: Dict[str, Any] = {"role": "assistant"}
    if tool_calls:
        clean_msg["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.name, "arguments": json.dumps(tc.input)}}
            for tc in tool_calls
        ]
        clean_msg["content"] = cleaned_text  # normally None alongside tool_calls
    else:
        clean_msg["content"] = cleaned_text or ""

    return TurnResult(text=cleaned_text, tool_calls=tool_calls, raw_assistant_message=clean_msg)

# Convert tool results into OpenAI tool message format.
def _openai_tool_results_message(results):
    return [{"role": "tool", "tool_call_id": r["id"], "content": json.dumps(r["output"])} for r in results]




###############








# Azure OpenAI provider implementation.
# Uses Azure deployment, endpoint, and API key.



#bgeb hagat azure 

class AzureOpenAIProvider(LLMProvider):
    def __init__(self, endpoint: Optional[str] = None, api_key: Optional[str] = None,
                 deployment: Optional[str] = None, api_version: Optional[str] = None):
        self.endpoint = (endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self.deployment = deployment or os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        self.api_version = api_version or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01")
        if not (self.endpoint and self.api_key and self.deployment):
            raise RuntimeError(
                "Azure OpenAI needs AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, "
                "and AZURE_OPENAI_DEPLOYMENT to be set."
            )


#bb3at el message el conv

    def send(self, messages, tools, system) -> TurnResult:
        oa_messages = [{"role": "system", "content": system}] + messages
        body = {"messages": oa_messages, "tools": _to_openai_tools(tools), "tool_choice": "auto"}
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json", "api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Azure OpenAI API error {e.code}: {e.read().decode('utf-8')}")
        return _parse_openai_response(data)




#bakhod nateg el tool f shape message 

    def build_tool_results_message(self, results):
        return _openai_tool_results_message(results)














# Hugging Face — free option (no card needed)

class HuggingFaceProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 base_url: str = "https://router.huggingface.co/v1"):
        self.api_key = api_key or os.environ.get("HF_TOKEN")
        self.model = model or os.environ.get("HF_MODEL", "openai/gpt-oss-120b")
        self.base_url = base_url
        if not self.api_key:
            raise RuntimeError("HF_TOKEN is not set.")

    def send(self, messages, tools, system) -> TurnResult:
        oa_messages = [{"role": "system", "content": system}] + messages
        body = {"model": self.model, "messages": oa_messages,
                "tools": _to_openai_tools(tools), "tool_choice": "auto"}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {self.api_key}",
             
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/124.0.0.0 Safari/537.36",
                "accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
           
            detail = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Hugging Face API error {e.code} for model '{self.model}': {detail}"
            ) from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Could not reach Hugging Face ({self.base_url}): {e.reason}") from None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"Hugging Face returned a non-JSON response (first 300 chars): {raw[:300]!r}"
            ) from None

        if "error" in data:
            
            raise RuntimeError(f"Hugging Face API error for model '{self.model}': {data['error']}")

        if "choices" not in data:
            raise RuntimeError(
                f"Unexpected Hugging Face response shape (no 'choices'): {json.dumps(data)[:300]}"
            )

        return _parse_openai_response(data)

    def build_tool_results_message(self, results):
        return _openai_tool_results_message(results)












# Mock provider, deterministic, offline, used by the eval harness


class MockProvider(LLMProvider):
    """Heuristic stand-in for an LLM's tool-calling behaviour. Only handles
    intent classification and multi-candidate disambiguation now — the
    yes/no confirmation gate for destructive actions lives in agent.py and
    never reaches this class at all."""

    def __init__(self):
        self._call_counter = 0
        self._pending_intent: Optional[str] = None
        self._pending_new_body: Optional[str] = None
        self._last_note_id: Optional[int] = None
        self._pending_disambiguation: Optional[dict] = None

    def _last_user_text(self, messages) -> str:
        for m in reversed(messages):
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                return m["content"]
        return ""

    def _last_tool_results(self, messages) -> List[dict]:
        if not messages:
            return []
        last = messages[-1]
        if last.get("role") == "user" and isinstance(last.get("content"), list):
            out = []
            for block in last["content"]:
                if block.get("type") == "tool_result":
                    out.append(json.loads(block["content"]))
            return out
        return []

    def _tc(self, name, **kwargs) -> ToolCall:
        self._call_counter += 1
        return ToolCall(id=f"mock_{self._call_counter}", name=name, input=kwargs)

    def send(self, messages, tools, system) -> TurnResult:
        text = self._last_user_text(messages)
        low = text.lower()
        last_results = self._last_tool_results(messages)

        def finish(txt):
            return TurnResult(text=txt, tool_calls=[], raw_assistant_message={"role": "assistant", "content": txt})

        def call(tc):
            return TurnResult(text=None, tool_calls=[tc], raw_assistant_message={"role": "assistant", "content": [tc]})

        if not last_results and self._pending_disambiguation is not None:
            pend = self._pending_disambiguation
            candidates = pend["notes"]
            chosen = None
            id_match = re.search(r"#?(\d+)", text)
            if id_match:
                cid = int(id_match.group(1))
                chosen = next((n for n in candidates if n["id"] == cid), None)
            if not chosen:
                for n in candidates:
                    if any(w in low for w in n["title"].lower().split() if len(w) > 3):
                        chosen = n
                        break
            if not chosen:
                listing = "\n".join(f"- #{n['id']}: {n['title']}" for n in candidates)
                return finish(f"Sorry, I still didn't catch which one — please give me the number:\n{listing}")
            self._pending_disambiguation = None
            if pend["intent"] == "delete":
                return call(self._tc("delete_note", note_id=chosen["id"]))
            return call(self._tc("update_note", note_id=chosen["id"], body=pend["new_body"]))

        # A tool call in THIS turn's loop asked us to preview a
        # destructive action (agent.py intercepted it) — just relay it. 
        
        if last_results and last_results[-1].get("needs_confirmation"):
            return finish(last_results[-1]["question"])

        #  Resolve a get_note result for a "that note" follow-up 

        if last_results and self._pending_intent == "followup_update" and last_results[-1].get("ok") \
                and "note" in last_results[-1]:
            n = last_results[-1]["note"]
            new_body = f"{n['body']} {self._pending_new_body}".strip()
            self._pending_intent = "update"
            return call(self._tc("update_note", note_id=n["id"], body=new_body))

        # Search results back: decide what to do next

        if last_results and "notes" in last_results[-1]:
            notes = last_results[-1]["notes"]
            if not notes:
                return finish(
                    "I couldn't find any notes matching that. Want to try different keywords, "
                    "a tag, or should I list your most recent notes instead?"
                )
            if len(notes) > 1 and self._pending_intent in ("delete", "update"):
                self._pending_disambiguation = {
                    "intent": self._pending_intent, "notes": notes, "new_body": self._pending_new_body,
                }
                listing = "\n".join(f"- #{n['id']}: {n['title']} ({n['snippet']})" for n in notes)
                return finish(f"I found {len(notes)} notes that match — which one did you mean?\n{listing}")
            if self._pending_intent == "delete":
                return call(self._tc("delete_note", note_id=notes[0]["id"]))
            if self._pending_intent == "update":
                return call(self._tc("update_note", note_id=notes[0]["id"], body=self._pending_new_body))
            if self._pending_intent == "summarize":
                titles = "; ".join(f"{n['title']} ({n['snippet']})" for n in notes)
                return finish(f"Here's a summary of {len(notes)} matching note(s): {titles}")
            listing = "\n".join(f"- #{n['id']}: {n['title']} [{', '.join(n['tags'])}]" for n in notes)
            return finish(f"Found {len(notes)} note(s):\n{listing}")

        if last_results and "deleted_id" in last_results[-1] and last_results[-1].get("ok"):
            return finish(f"Deleted note #{last_results[-1]['deleted_id']}. You can say 'undo' to restore it.")

        if last_results and "flagged" in last_results[-1]:
            flagged = last_results[-1]["flagged"]
            if not flagged:
                return finish(f"No recurring keywords found across your '{last_results[-1]['tag']}' notes.")
            top = "; ".join(f"'{f['keyword']}' in {len(f['note_ids'])} notes" for f in flagged[:5])
            return finish(f"Possible recurring issues under '{last_results[-1]['tag']}': {top}")

        if last_results and "undone" in last_results[-1] and last_results[-1].get("ok"):
            return finish(last_results[-1]["detail"])

        if last_results and "note" in last_results[-1] and "needs_confirmation" not in last_results[-1] \
                and last_results[-1].get("ok"):
            n = last_results[-1]["note"]
            action = "Saved" if self._pending_intent == "add" else "Updated"
            return finish(f"{action} note #{n['id']}: \"{n['title']}\".")

        if last_results and last_results[-1].get("error"):
            return finish(f"That didn't work: {last_results[-1]['error']} Want to try again with more detail?")

        # Fresh user turn: classify intent 
        self._pending_intent = None

        if ("save" in low or "add a note" in low or "jot down" in low) and "note" in low:
            tag_match = re.search(r",?\s*tag(?:ged)? it as ['\"]?([\w\-]+)['\"]?", text, re.I)
            tags = [tag_match.group(1)] if tag_match else []
            core = re.sub(r",?\s*tag(?:ged)? it as ['\"]?[\w\-]+['\"]?", "", text, flags=re.I).strip(" .")
            core = re.sub(r"^(save|add|jot down)\s+a\s+note\s+about\s+", "", core, flags=re.I)
            core = re.sub(r"^(save|add|jot down)\s+a\s+note[:\-]?\s*", "", core, flags=re.I)
            parts = re.split(r"\s*[-—]\s+|\s*:\s+", core, maxsplit=1)
            if len(parts) == 2:
                title, body = parts
            else:
                title, body = core[:40], core
            self._pending_intent = "add"
            return call(self._tc("add_note", title=title.strip().capitalize(), body=body.strip(), tags=tags))

        if low.strip() in ("undo", "undo that", "undo last action", "please undo that"):
            return call(self._tc("undo_last_action"))

        if "recurring" in low or "predict" in low and "maintenance" in low:
            tag_match = re.search(r"tag(?:ged)? ['\"]?(\w+)", low)
            return call(self._tc("list_recurring_issues", tag=(tag_match.group(1) if tag_match else None)))

        if "add a deadline to that" in low or ("deadline" in low and "that" in low) or "add that" in low:
            self._pending_intent = "followup_update"
            addendum_match = re.search(r"to that:?\s*(.+)", text, re.I)
            self._pending_new_body = addendum_match.group(1).strip() if addendum_match else text
            return call(self._tc("get_note", note_id=self._last_note_id))

        if re.search(r"\bdelete\b|\bremove\b", low):
            self._pending_intent = "delete"
            q = re.sub(r".*(delete|remove) (the note (about|on) )?", "", text, flags=re.I).strip(" ?.!")
            return call(self._tc("search_notes", query=q))

        if re.search(r"\bupdate\b|\bchange\b|now (the )?meeting", low):
            self._pending_intent = "update"
            say_match = re.search(r"to say (.+)$", text, re.I)
            self._pending_new_body = say_match.group(1).strip(" ?.!") if say_match else text
            q = re.sub(r".*(update|change) (my |the )?", "", text, flags=re.I).split(" to say")[0].strip(" ?.!")
            q = re.sub(r"\bnotes?\b", "", q, flags=re.I).strip()
            return call(self._tc("search_notes", query=q))

        if "summari" in low:
            self._pending_intent = "summarize"
            tag_match = re.search(r"tagged as (\w+)|tag(?:ged)? ['\"]?(\w+)", low)
            tag = next((g for g in (tag_match.groups() if tag_match else []) if g), None)
            return call(self._tc("search_notes", tag=tag))

        if re.search(r"\bwhat did i write\b|\bfind\b|\bshow\b|\bsearch\b|\blist\b", low):
            self._pending_intent = "search"
            tag_match = re.search(r"tag(?:ged)? ['\"]?(\w+)", low)
            if tag_match:
                return call(self._tc("search_notes", tag=tag_match.group(1)))
            topic = re.sub(r".*(about|for|on)\s+", "", text, flags=re.I).strip(" ?.!")
            return call(self._tc("search_notes", query=topic))

        return finish(
            "I'm not sure what you'd like to do. You can ask me to save a note, "
            "search/list your notes, update or delete one, undo the last action, "
            "check for recurring issues under a tag, or summarize a tag."
        )

    def build_tool_results_message(self, results):
        content = [{"type": "tool_result", "tool_use_id": r["id"], "content": json.dumps(r["output"])} for r in results]
        return {"role": "user", "content": content}


def get_provider(name: Optional[str] = None) -> LLMProvider:
    name = (name or os.environ.get("LLM_PROVIDER", "mock")).lower()
    if name in ("azure_openai", "azure"):
        return AzureOpenAIProvider()
    if name in ("huggingface", "hf"):
        return HuggingFaceProvider()
    if name == "mock":
        return MockProvider()
    raise ValueError(f"Unknown LLM_PROVIDER '{name}'. Use azure_openai | huggingface | anthropic | mock.")
