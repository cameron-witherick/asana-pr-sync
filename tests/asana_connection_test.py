"""
Live connection test for the Asana + GitHub bot.
 
It checks three things, in order:
  1. The token works (who am I?)
  2. The bot can see the project and its columns
  3. The bot can read a task and get its web link
  4. The bot can read the task ID
"""

import os
import sys
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv


 #Load .env from the same folder as this file. override=False means anything

load_dotenv()

BASE = os.environ.get("BASE", "")
PROJECT_GID = os.environ.get("ASANA_PROJECT_GID", "")
TOKEN = os.environ.get("ASANA_TOKEN", "")

# Column names
EXPECTED_COLUMNS=["Njs-main", "staging", "main"]

needs_token = pytest.mark.skipif(not TOKEN, reason="ASANA_TOKEN not set")


def get(path, **params):
    #GET an Asana endpoint and return the response (never raises on 4xx).
    try:
        return requests.get(
            f"{BASE}{path}",
            headers= {"Authorization": f"Bearer {TOKEN}"},
            params= params,
            timeout=20,
        )
    except requests.RequestException as e:
        pytest.fail(f"Could not reach Asana at all (network/proxy/VPN issue): {type(e).__name__}")

def explain(resp):
    #Turn a failed response into a plain-English hint.
    hints={
        401: "Token rejected. Re-copy it (no spaces, no quotes) or make a new one.",
        403: "Forbidden. Add the bot user to the project as a member that can edit.",
        404: "Not found. Check the project ID, and that the bot user is in the project.",
        429: "Rate limited by Asana. Wait a minute and try again.",
    }
    return hints.get(resp.status_code , f"Unexpected status {resp.status_code}.")

@needs_token
def test_1_token_works():
    r= get("/users/me", opt_fields = "name,email")
    assert r.status_code==200, explain(r)
    me = r.json()["data"]
    print(f"\n Logged in as: {me.get('name')} <{me.get('email')}>")

@needs_token
def test_2_bot_can_see_project_columns():
    r = get(f"/projects/{PROJECT_GID}/sections", opt_fields="name")
    assert r.status_code==200, explain(r)
    sections= r.json()["data"]

    names = [s["name"] for s in sections]
    print("\n Columns found: ")
    for s in sections:
        print(f"    {s["name"]!r} (id {s['gid']})")

    missing = [c for c in EXPECTED_COLUMNS if c not in names]
    assert not missing, (
        f"These columns were not found (names must match exactly, including "
        f"capitals): {missing}. Found: {names}"
    )

@needs_token
def test_3_bot_can_read_a_tasks_and_their_link():
    r = get(f"/projects/{PROJECT_GID}/tasks", opt_fields= "name,permalink_url", limit=100)
    assert r.status_code==200, explain(r)
    tasks = r.json()["data"]
    if not tasks:
        pytest.skip("The project has no tasks yet. Please create one and run again")
    #task = tasks[0]
    for task in tasks:
        assert task.get("permalink_url", "").startswith("https://app.asana.com/"),(
            "Task came back without permalink_url. Make sure opt_fields includes it."
        )
        print(f"\n Read Task:   {task['name']!r}\n  Link: {task['permalink_url']}")


@needs_token
def test_4_bot_can_read_custom_fields():
    r = get(f"/projects/{PROJECT_GID}/tasks", opt_fields=("name,permalink_url,"
                                                            "custom_fields.name,custom_fields.display_value,"
                                                            "custom_fields.enabled,custom_fields.representation_type,"
                                                            "custom_fields.id_prefix"), limit=100)
    assert r.status_code ==200, explain(r)
    tasks= r.json()["data"]
    if not tasks:
        pytest.skip("The project has no tasks yet. Please create one and run again")
    for task in tasks:
        print(f"\nTask: {task['name']}")
        print(f"    Link: {task['permalink_url']}")
        for field in task["custom_fields"]:
            value = field.get("display_value") or "(empty)"
            notes=[]
            if field.get("id_prefix"):
                notes.append(f"ID field, prefix {field['id_prefix']!r}")
            if not field.get("enabled", True):
                notes.append("disabled")
            note =  f"   [{', '.join(notes)}]" if notes else ""
            print(f"  {field['name']}: {value}{note}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))