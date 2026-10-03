import os
import sys
import re
import requests
from dotenv import load_dotenv


load_dotenv()
BASE = "https://app.asana.com/api/1.0"

#Matches Tasks IDs like "MMS-1" or "ABC-123"
#Anything not matching this format is skipped.
ID_PATTERN = re.compile(r"^[A-Z]+-\d+$") 


class AsanaClient:
    """
    Fetches tasks from a Asana Project and maps their custom ID to the 
    task's gid and URL, so a github commit message referencing the ID 
    can be matched to the right task
    """

    def __init__(self):
        self.project_gid = os.environ.get("ASANA_PROJECT_GID", "")
        self.token= os.environ.get("ASANA_TOKEN", "")
        self.idName = os.environ.get("ID_FIELD_NAME", "")

        #Fail fast if a required variable is missing or empty
        required= {"ASANA_TOKEN": self.token, "ASANA_PROJECT_GID": self.project_gid}
        missing= [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing environment variable(s): {', '.join(missing)}")

        #Fetches every task in the project and then builds a lookup table 
        self.tasks= self.getTasks()
        self.idLookUp = self.buildLookup()

        return self.idLookUp


    def get(self, path, **params):
        #GET an Asana endpoint and return the response (never raises on 4xx).
        try:
            return requests.get(
                f"{BASE}{path}",
                headers= {"Authorization": f"Bearer {self.token}"}, #personal access token auth
                params= params, #query string, e.g. limit, opt_fields, offset
                timeout=20,
            )
        except requests.RequestException as e:
            print(f"Could not reach Asana at all:   {type(e).__name__}", file=sys.stderr)
            return None

    def explain(self, resp): 
        #Turn a failed response into a plain-English hint.
        hints={
                401: "Token rejected. Re-copy it (no spaces, no quotes) or make a new one.",
                403: "Forbidden. Add the bot user to the project as a member that can edit.",
                404: "Not found. Check the project ID, and that the bot user is in the project.",
                429: "Rate limited by Asana. Wait a minute and try again.",
            }
        return hints.get(resp.status_code , f"Unexpected status {resp.status_code}.")


    def getTasks(self):
        # Fetch all tasks in the project, following Asana's pagination.
        tasks=[]
        params = {
            "limit": 100, #max page size asana allows 
            "opt_fields": (
                "name,permalink_url,"
                "custom_fields.name,custom_fields.display_value,"
                "custom_fields.enabled,custom_fields.representation_type,"
                "custom_fields.id_prefix"
            )
        }
        while True:
            r = self.get(f"/projects/{self.project_gid}/tasks", **params)
            assert r.status_code==200, self.explain(r) 
            body = r.json()
            tasks.extend(body["data"])# Add this page of tasks to the full list


            # Asana includes "next_page" while more results remain.
            # If it's missing/null, we've reached the last page.
            next_page = body.get("next_page")
            if not next_page:
                break
            params["offset"] = next_page["offset"] #pass the offset to request the next page

        # Handle an empty project
        if not tasks:
            print("The project has no tasks yet. Please create one and run again")
            return None
        return tasks

    def buildLookup(self):
        # Build a dict mapping each task ID to its gid and URL:
        lookup={}
        for task in self.tasks:
            #looks through the tasks custom fields for the ID-field
            for field in task.get("custom_fields", []):
                if field.get("name") != self.idName:    # Skip fields that aren't the ID field
                    continue
                value = field.get("display_value")
                if not value or not ID_PATTERN.match(value):   # Skip tasks with an empty ID or one that isn't in the "ABC-123" format
                    break

                if value in lookup:
                    print(f"Duplicate ID {value} on task {task['gid']}, ignoring", file=sys.stderr)
                    break
                lookup[value] = {'gid': task['gid'],
                                 'url': task['permalink_url']}
                break
        return lookup



"""
if __name__ == "__main__":
    client = AsanaClient()
    print(client)
"""