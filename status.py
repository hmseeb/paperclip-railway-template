#!/usr/bin/env python3
"""Print every service's latest deployment status. Usage: status.py <projectId> [--wait]"""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402

Q = """query($id: String!) { project(id: $id) { services { edges { node { name
  serviceInstances { edges { node { latestDeployment { id status }
  domains { serviceDomains { domain } } } } } } } } } }"""


def states(pid):
    out = []
    for e in rw.gql(Q, {"id": pid})["project"]["services"]["edges"]:
        for i in e["node"]["serviceInstances"]["edges"]:
            d = i["node"]["latestDeployment"] or {}
            doms = i["node"]["domains"]["serviceDomains"]
            out.append((e["node"]["name"], d.get("status"), d.get("id"), doms[0]["domain"] if doms else None))
    return out


if __name__ == "__main__":
    pid = sys.argv[1]
    for _ in range(90 if "--wait" in sys.argv else 1):
        s = states(pid)
        print(s, flush=True)
        if all(x[1] in ("SUCCESS", "FAILED", "CRASHED", "REMOVED") for x in s):
            break
        time.sleep(10)
