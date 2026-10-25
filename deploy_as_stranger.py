#!/usr/bin/env python3
"""Clicks the deploy button the way a stranger would: no projectId, fresh project.
Everything on the Paperclip deploy form has a default or a generator, so the stranger
path submits unchanged, which is exactly what this does. Polls until every
service reaches a terminal state, then prints project id and service states.
"""
import json
import pathlib
import sys
import time
sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402

TEMPLATE_ID = sys.argv[1] if len(sys.argv) > 1 else "dae7b86e-7cdb-4d30-a4c3-1342684fb4e6"  # optional: scratch template id
WORKSPACE_ID = "d10da65a-297f-4ba4-8cef-2fa9bb45fdef"  # My Projects: Auromations cannot create projects while billing is UNPAID

config = rw.gql(
    "query($id: String!) { template(id: $id) { serializedConfig } }",
    {"id": TEMPLATE_ID},
)["template"]["serializedConfig"]
if isinstance(config, str):
    config = json.loads(config)

result = rw.gql(
    """mutation($input: TemplateDeployV2Input!) {
         templateDeployV2(input: $input) { projectId workflowId }
       }""",
    {"input": {"templateId": TEMPLATE_ID, "workspaceId": WORKSPACE_ID, "serializedConfig": config}},
)["templateDeployV2"]
project_id = result["projectId"]
print("fresh project:", project_id, flush=True)

states = []
project = None
for _ in range(90):  # 15 min ceiling: multi-GB image pulls on a cold project
    time.sleep(10)
    project = rw.gql(
        """query($id: String!) {
             project(id: $id) {
               name
               environments { edges { node { id name } } }
               services { edges { node {
                 id name
                 serviceInstances { edges { node {
                   latestDeployment { id status }
                   domains { serviceDomains { domain } }
                 } } }
               } } }
             }
           }""",
        {"id": project_id},
    )["project"]
    states = []
    for edge in project["services"]["edges"]:
        node = edge["node"]
        for inst in node["serviceInstances"]["edges"]:
            dep = inst["node"]["latestDeployment"]
            doms = inst["node"]["domains"]["serviceDomains"]
            states.append((node["name"], dep["status"] if dep else "none",
                           doms[0]["domain"] if doms else None))
    terminal = [s for s in states if s[1] in ("SUCCESS", "FAILED", "CRASHED")]
    print(f"{len(terminal)}/{len(states)} terminal:", states, flush=True)
    if states and len(terminal) == len(states):
        break
env_id = project["environments"]["edges"][0]["node"]["id"]
print(json.dumps({"projectId": project_id, "environmentId": env_id, "states": states}, indent=2))
