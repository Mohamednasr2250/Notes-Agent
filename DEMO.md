# Demo: Real Conversations, Unedited

Everything below is copy-pasted from actual runs against real AI models —
not the offline test mode. Organized to show the strongest results first.

## 1. Reasoning over notes — spotting a contradiction

The task brief specifically calls out "Do I have any notes that
contradict each other?" as an example of reasoning over notes, not just
retrieving them. Here it is actually happening:

```
you> i want to search note about portugal
agent> Got it — there are two notes that mention Portugal:
| ID | Title                                | Snippet |
|----|--------------------------------------|---------|
| 5  | Portugal to face Spain in World Cup  | "Portugal will play against Spain in the upcoming World Cup match." |
| 4  | Portugal has Cristiano Ronaldo       | "Portugal is the country of Cristiano Ronaldo." |
Which one would you like to open, update, or do something else with?

you> add new note with title mo and body is mohamed is good
agent> Your new note has been saved:
- Title: mo
- Body: mohamed is good
It's stored as note #8.

you> Do I have any notes that contradict each other?
agent> I checked all of your notes and found a direct contradiction:
| Note ID | Title   | Body |
|---------|---------|------|
| 6       | mohamed | "mohamed is not good" |
| 8       | mo      | "mohamed is good" |
These two statements say opposite things about Mohamed's status. The
other notes (the Portugal facts, the maintenance items, the grocery list,
etc.) don't conflict with each other.
```

This is real reasoning across multiple notes' content, not a keyword
match — nothing in the tools returns "contradiction" as data; the model
had to compare two separate notes' meaning itself.

## 2. Natural conversation, not just commands

```
you> how are u
agent> I'm doing great, thanks for asking! How can I help you with your notes today?

you> thank u
agent> You're welcome! Just let me know if you need anything else.

you> hi
agent> Hi there! How can I help you with your notes today?
```

## 3. Full walkthrough — add, follow-up, disambiguation, undo, recurring issues

```
you> Save a note about a leaking radiator in Flat 6, tag it as maintenance
agent> Got it! I've saved a note titled "Leaking radiator in Flat 6" with the body you
provided and tagged it maintenance.

you> Actually, add to that: tenant says it's getting worse, needs urgent attention
agent> Sure thing — here's the updated version I'd apply to the radiator note:
Current body: "Leaking radiator reported in Flat 6. Needs inspection and repair."
Proposed new body: "...Tenant says it's getting worse and needs urgent attention."
If that looks good, just let me know and I'll update the note.

you> yes
agent> Done — updated note #3: "Leaking radiator in Flat 6".

you> Delete the note about Flat 6
agent> I see two maintenance notes that mention Flat 6:
- ID 3: Leaking radiator in Flat 6
- ID 4: Broken window latch in Flat 6
Which one would you like to delete?

you> the radiator one
agent> Ready to delete the radiator note (ID 3). Just reply "yes" to confirm.

you> yes
agent> Done — deleted note #3. Say 'undo' if that was a mistake.

you> undo
agent> Undo complete — the radiator note (ID 3) has been restored.

you> Check for recurring issues tagged maintenance
agent> I scanned your maintenance notes and found "leaking" and "radiator" appear in
notes #3 (Flat 6) and #5 (Flat 9). This suggests a recurring radiator-leak issue
across flats.
```





## 4. Another Context-aware conversation across multiple turns





```
you> i want to search note about portugal
agent> Got it—there are two notes that mention **Portugal**:

| ID | Title | Snippet |
|----|-------------------------------|----------------------------------------------|
| 5 | Portugal to face Spain in World Cup | “Portugal will play against Spain in the upcoming World Cup match.” |
| 4 | Portugal has Cristiano Ronaldo | “Portugal is the country of Cristiano Ronaldo.” |

Which one would you like to open, update, or do something else with? Let me know the ID (5 or 4) or describe what you’d like to do.

you> portugal and spain
agent> It looks like the note that mentions **both Portugal and Spain** is:

| ID | Title | Snippet |
|----|-------------------------------|----------------------------------------------|
| **5** | Portugal to face Spain in World Cup | “Portugal will play against Spain in the upcoming World Cup match.” |

Is that the one you’d like to view, edit, or do something else with? Let me know what you’d like to do with note 5.

you> i want to delete it
agent> Sure thing—deleting note **5** will remove the entry titled **“Portugal to face Spain in World Cup.”** Once deleted, it will no longer appear in anrches or listings (you can undo it later if needed).

Do you want me to proceed with deleting this note?

you> no
agent> No problem—I'll leave the note untouched. Let me know if you’d like to view it, edit it, or do anything else with it (or with any other note).

you> i want to update it
agent> Got it. Here’s the current content of note 5:

- **Title:** *Portugal to face Spain in World Cup*  
- **Body:** *Note: Portugal will play against Spain in the upcoming World Cup match.*  
- **Tags:** *(none)*  

What would you like to change? You can give a new title, new body text, and/or add tags (e.g., `["sports"]`). Let me know the updates, and I’ll show you aiew before applying them.

you> update the word spain with egypt
agent> Here’s the preview of the updated note 5:

- **New title:** *Portugal to face Egypt in World Cup*  
- **New body:** *Note: Portugal will play against Egypt in the upcoming World Cup match.*  
- **Tags:** *(unchanged – none)*  

Shall I go ahead and apply these changes?

you> yes
agent> Something went wrong on my end (Hugging Face API error 402 for model 'openai/gpt-oss-120b:together': {"error":"You have depleted your monthly incluredits. Purchase pre-paid credits to continue using Inference Providers. Alternatively, subscribe to PRO to get 20x more included usage."}). Let's try thain.

you> what?
agent> Just to be clear — I'll update note #5 with {'title': 'Portugal to face Egypt in World Cup', 'body': 'Note: Portugal will play against Egypt in theming World Cup match.'} — go ahead? (yes/no)

you> yes
agent> Done — updated note #5: "Portugal to face Egypt in World Cup".

you> i want to undo last action
agent> The last change has been undone. Note 5 is now back to its original title **“Portugal to face Spain in World Cup”** and its original body. Let me kf you’d like anything else—view, edit, delete, or add a new note.
```





## 5. A real limit we hit, and how the code handled it

Mid-conversation, this happened:

```
you> yes
agent> Something went wrong on my end (Hugging Face API error 402: You have depleted
your monthly included credits...). Let's try that again.

you> what?
agent> Just to be clear — I'll update note #5 with {...} — go ahead? (yes/no)

you> yes
agent> Done — updated note #5: "Portugal to face Egypt in World Cup".
```

What happened: Hugging Face's free monthly quota ran out mid-session. The
code has automatic retry logic for temporary problems (rate limits,
occasional bad responses from the model), but a used-up monthly quota
isn't temporary — retrying won't fix it, so the agent correctly shows a
clear error instead of hanging or pretending it worked. Note the
confirmation was never lost or skipped: asking "yes" again a moment later
picked up right where it left off, safely, because the confirmation check
happens in code, not by trusting the model to remember.

## 6. Bonus: MCP + LangGraph

The same notes tools, exposed through the MCP standard, driven by a
LangGraph agent instead of the app's normal chat loop. Run twice, saved
real notes both times:

```
python bonus/langgraph_mcp_agent.py

Your note has been saved:
- Title: Leaking radiator in Flat 6
- Body: Reported a leaking radiator in Flat 6. Immediate inspection required.
- Tag: maintenance
- Note ID: 9
```
```
python bonus/langgraph_mcp_agent.py

Your note has been saved:
- Title: Leaking radiator in Flat 6
- Body: Investigated a leaking radiator in Flat 6. Water pooling near the base.
- Tag: maintenance
- Note ID: 10
```

Checked directly in the database afterward — both notes #9 and #10 were
really there, not just claimed in the chat reply.

## 7. Bonus: Semantic search + LangGraph

Finds notes by meaning, not exact words — searching "project deadline"
correctly matched a note that never uses the word "deadline":

```
python bonus/langgraph_semantic_search.py

**What matched your search**
| Note | Score | Why it's relevant |
|------|-------|--------------------|
| #1 | 0.37 | This note talks about a "launch plan" and says the "final report must be
shipped by Friday or we lose the client." That is essentially a project deadline, even
though the exact phrase "project deadline" isn't used. |
| #2 | 0.01 | This note is about buying milk and eggs. Almost no connection to a
deadline, which is why its similarity score is very low. |

Bottom line: The first note is the only one that meaningfully matches your query about
a project deadline. The second note is unrelated.
```

The score (0.37 vs 0.01) is a real number calculated by comparing meaning,
not a guess — proof the matching is genuinely semantic.

## 8. Multi-user isolation

Two separate users, same database file, tested directly in two separate
terminals:

```
$env:USER_ID = "alice"
python -m notes_agent.cli
notes agent ready. (provider: huggingface, db: notes.db9, user: alice)

you> Save a note about the lift servicing at Block C - contractor visited
today, all checks passed, tag it as maintenance
agent> Your note has been saved:
- Title: Lift servicing at Block C
- Body: Contractor visited today, all checks passed.
- Tags: maintenance
```

```
$env:USER_ID = "bob"
python -m notes_agent.cli
notes agent ready. (provider: huggingface, db: notes.db9, user: bob)

you> What did i write about the lift?
agent> I don't have any notes that mention the lift. Would you like to
create a new note about it or search using a different keyword?
```

```
$env:USER_ID = "alice"
python -m notes_agent.cli
notes agent ready. (provider: huggingface, db: notes.db9, user: alice)

you> what did i write about the lift
agent> Here's the note you have about the lift:
Title: Lift servicing at Block C
Body: Contractor visited today, all checks passed.
```

Bob correctly saw nothing. Alice correctly saw her own note. Same
database file, two different users, genuinely isolated. (A few Hugging
Face quota errors show up in the raw session in between these — that's
the same free-tier monthly limit from section 4, unrelated to isolation;
once a request actually got through, the result was correct both times.)


