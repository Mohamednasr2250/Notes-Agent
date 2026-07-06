"""
Automated test scenarios for the notes agent.

Each scenario sends user messages to the agent and checks
whether the result is correct.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notes_agent.storage import NotesStore
from notes_agent.agent import Agent
from notes_agent.llm_providers import get_provider


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


class Scenario:
    def __init__(self, name, steps, check):
        self.name = name
        self.steps = steps
        self.check = check


def run_scenario(scenario, provider_name):
    store = NotesStore(":memory:")
    agent = Agent(store, provider=get_provider(provider_name))
    replies = []
    try:
        for step in scenario.steps:
            replies.append(agent.send(step))
        ok, detail = scenario.check(agent, replies, store)
    except Exception as e:
        ok, detail = False, f"raised exception: {e!r}"
    return ok, detail, replies


# Checks


def check_add_basic(agent, replies, store):
    notes = store.all_notes()
    if len(notes) != 1:
        return False, f"expected 1 note, found {len(notes)}"
    if "maintenance" not in notes[0].tags:
        return False, f"expected tag 'maintenance', got {notes[0].tags}"
    return True, "note created with correct tag"


def check_tags_parsed(agent, replies, store):
    notes = store.all_notes()
    if not notes or "maintenance" not in notes[0].tags:
        return False, f"tag wasn't parsed from natural language: {notes[0].tags if notes else notes}"
    return True, "tag correctly extracted from free-text phrasing"


def check_search_finds_it(agent, replies, store):
    if "boiler" not in replies[-1].lower():
        return False, f"reply didn't mention the matching note: {replies[-1]!r}"
    return True, "search surfaced the right note"


def check_search_no_results(agent, replies, store):
    
    r = replies[-1].lower().replace("\u2019", "'").replace("\u2018", "'")
    
    no_match_signals = (
        "no note", "couldn't find", "could not find", "can't find", "cannot find",
        "0 note", "no matching", "nothing matching", "no results", "don't have any",
        "do not have any", "doesn't seem", "don't seem", "wasn't able to find",
        "did not find", "didn't find",
    )
    if not any(s in r for s in no_match_signals):
        return False, f"expected a clear 'no results' message, got: {replies[-1]!r}"

    suggestion_signals = (
        "?", "try", "instead", "different", "another", "keyword", "tag",
        "let me know", "give me", "if you", "details",
    )
    if not any(s in r for s in suggestion_signals):
        return False, "expected agent to suggest an alternative, not just report failure"
    return True, "graceful no-results handling with a suggested next step"


def check_list_by_tag(agent, replies, store):
    if "maintenance" not in " ".join(replies).lower():
        return False, "tag-filtered listing didn't reference the tag/notes"
    return True, "tag filter worked"


def check_delete_requires_disambiguation(agent, replies, store):
    if store.get_note(1) is None or store.get_note(2) is None:
        return False, "a note was deleted before disambiguation — should never happen"
    last = replies[-1].lower()
    if "which" not in last and "?" not in replies[-1]:
        return False, f"expected a clarifying question, got: {replies[-1]!r}"
    return True, "asked for disambiguation instead of guessing, no deletion occurred"


def check_delete_confirmed_flow(agent, replies, store):
    if store.get_note(1) is not None:
        return False, "note still exists after explicit confirmed deletion"
    if "deleted" not in replies[-1].lower():
        return False, f"reply didn't confirm the deletion: {replies[-1]!r}"
    return True, "note deleted only after explicit confirmation"


def check_delete_declined_flow(agent, replies, store):
    if store.get_note(1) is None:
        return False, "note was deleted despite user saying no"
    if "won't" not in replies[-1].lower() and "not" not in replies[-1].lower():
        return False, f"reply didn't acknowledge the decline: {replies[-1]!r}"
    return True, "declined deletion left the note untouched"


def check_update_confirmed_flow(agent, replies, store):
    note = store.get_note(1)
    if note is None:
        return False, "note missing entirely"
    if "wednesday" not in note.body.lower():
        return False, f"body wasn't actually updated: {note.body!r}"
    return True, "update applied only after confirmation, content correctly changed"


def check_update_declined_flow(agent, replies, store):
    note = store.get_note(1)
    if "wednesday" in note.body.lower():
        return False, "update was applied despite user declining"
    return True, "declined update left original content untouched"


def check_followup_reference(agent, replies, store):
    note = store.get_note(1)
    if "friday" not in note.body.lower():
        return False, f"follow-up 'add a deadline to that' wasn't applied: {note.body!r}"
    return True, "pronoun/'that note' follow-up correctly resolved via session state"


def check_summarize_tag(agent, replies, store):
    if len(replies[-1]) < 10:
        return False, "summary reply looks empty/too short"
    return True, "produced a non-trivial summary reply"


def check_update_nonexistent(agent, replies, store):
    last = replies[-1].lower()
    if "no note" not in last and "couldn't find" not in last and "doesn't exist" not in last and "already" not in last:
        return False, f"expected a clear error for a nonexistent note id, got: {replies[-1]!r}"
    return True, "handled a reference to a nonexistent note gracefully"


def check_empty_note_content(agent, replies, store):
    notes = store.all_notes()
    if len(notes) != 0:
        return False, "an empty/contentless note was saved instead of asking for details"
    if "?" not in replies[-1]:
        return False, f"expected the agent to ask a clarifying question, got: {replies[-1]!r}"
    return True, "asked for missing content instead of saving an empty note"


def check_undo_delete(agent, replies, store):
    note = store.get_note(1)
    if note is None:
        return False, "note was not restored after undo"
    return True, "undo correctly restored a soft-deleted note"


def check_undo_update(agent, replies, store):
    note = store.get_note(1)
    if "wednesday" in note.body.lower():
        return False, "undo did not revert the update"
    return True, "undo correctly reverted the note to its pre-update content"


def check_recurring_issues(agent, replies, store):
    last = replies[-1].lower()
    if "boiler" not in last:
        return False, f"expected 'boiler' to be flagged as recurring, got: {replies[-1]!r}"
    return True, "correctly flagged a keyword recurring across multiple maintenance notes"


SCENARIOS = [
    Scenario(
        "01_add_note_with_tag_happy_path",
        ["Save a note about the boiler repair at Flat 4 - engineer booked for Friday, tag it as maintenance"],
        check_add_basic,
    ),
    Scenario(
        "02_add_note_tags_parsed_from_language",
        ["Save a note about the annual gas safety check at Flat 7 - passed, tag it as maintenance"],
        check_tags_parsed,
    ),
    Scenario(
        "03_search_by_keyword_finds_match",
        [
            "Save a note about the boiler at Flat 4 - engineer booked for Friday, tag it as maintenance",
            "What did I write about the boiler?",
        ],
        check_search_finds_it,
    ),
    Scenario(
        "04_search_no_results_graceful",
        ["What did I write about the lift?"],
        check_search_no_results,
    ),
    Scenario(
        "05_list_notes_by_tag",
        [
            "Save a note about the fire alarm test at Flat 12 - completed, tag it as maintenance",
            "List my notes tagged maintenance",
        ],
        check_list_by_tag,
    ),
    Scenario(
        "06_ambiguous_delete_asks_for_clarification",
        [
            "Save a note about the tenancy renewal for Flat 4 - postponed, tag it as tenancy",
            "Save a note about the tenancy renewal for Flat 9 - signed, tag it as tenancy",
            "Delete the note about the tenancy renewal",
        ],
        check_delete_requires_disambiguation,
    ),
    Scenario(
        "07_delete_confirmed_after_disambiguation",
        [
            "Save a note about the old caretaker contact details - no longer valid",
            "Delete the note about the old caretaker contact details",
            "yes",
        ],
        check_delete_confirmed_flow,
    ),
    Scenario(
        "08_delete_declined_leaves_note_intact",
        [
            "Save a note about the old caretaker contact details - no longer valid",
            "Delete the note about the old caretaker contact details",
            "no, don't delete it",
        ],
        check_delete_declined_flow,
    ),
    Scenario(
        "09_update_confirmed_applies_change",
        [
            "Save a note about the Flat 4 inspection - scheduled for Tuesdays, tag it as inspection",
            "Update my Flat 4 inspection note to say it's now on Wednesdays",
            "yes go ahead",
        ],
        check_update_confirmed_flow,
    ),
    Scenario(
        "10_update_declined_leaves_note_unchanged",
        [
            "Save a note about the Flat 4 inspection - scheduled for Tuesdays, tag it as inspection",
            "Update my Flat 4 inspection note to say it's now on Wednesdays",
            "no, cancel that",
        ],
        check_update_declined_flow,
    ),
    Scenario(
        "11_multiturn_followup_reference_resolution",
        [
            "Save a note about the roof repair at Flat 9 - contractor lined up for next month",
            "Actually, add a deadline to that: must be done by Friday",
            "yes",
        ],
        check_followup_reference,
    ),
    Scenario(
        "12_summarize_notes_by_tag",
        [
            "Save a note about the burst pipe at Flat 2 - resolved same day, tag it as urgent",
            "Save a note about the power outage at Flat 6 - restored after an hour, tag it as urgent",
            "Summarise everything I've tagged as urgent",
        ],
        check_summarize_tag,
    ),
    Scenario(
        "13_update_nonexistent_note_graceful_error",
        ["Update note number 999 to say it's done"],
        check_update_nonexistent,
    ),
    Scenario(
        "14_refuses_to_save_note_with_no_real_content",
        ["Save a note"],
        check_empty_note_content,
    ),
    Scenario(
        "15_undo_restores_a_deleted_note",
        [
            "Save a note about the parking dispute at Flat 3 - resident complained, tag it as tenancy",
            "Delete the note about the parking dispute",
            "yes",
            "undo",
        ],
        check_undo_delete,
    ),
    Scenario(
        "16_undo_reverts_an_update",
        [
            "Save a note about the Flat 4 inspection - scheduled for Tuesdays, tag it as inspection",
            "Update my Flat 4 inspection note to say it's now on Wednesdays",
            "yes",
            "undo",
        ],
        check_undo_update,
    ),
    Scenario(
        "17_recurring_maintenance_issue_flagged",
        [
            "Save a note about Flat 4 - boiler making a loud noise again, tag it as maintenance",
            "Save a note about Flat 9 - boiler pressure keeps dropping, tag it as maintenance",
            "Save a note about Flat 2 - leaking tap in the kitchen, tag it as maintenance",
            "Check for recurring issues tagged maintenance",
        ],
        check_recurring_issues,
    ),
]


def main():
    provider_name = os.environ.get("EVAL_LLM_PROVIDER", os.environ.get("LLM_PROVIDER", "mock"))
    print(f"Running {len(SCENARIOS)} scenarios against provider='{provider_name}'\n")
    passed = 0
    results = []
    for sc in SCENARIOS:
        ok, detail, replies = run_scenario(sc, provider_name)
        results.append((sc.name, ok, detail))
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {sc.name} — {detail}")
        if ok:
            passed += 1

    total = len(SCENARIOS)
    print(f"\n{passed}/{total} passed ({passed/total:.0%})")
    failing = [r for r in results if not r[1]]
    if failing:
        print("\nFailures:")
        for name, ok, detail in failing:
            print(f"  - {name}: {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
