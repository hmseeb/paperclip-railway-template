#!/usr/bin/env python3
"""Builds the live Paperclip source project in Auromations (the regeneration master).
Topology: Postgres (Railway postgres-ssl:17) + Paperclip (official upstream image).
See template.json for the rationale on every variable.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402
from spec import IMAGE, PG_IMAGE, PAPERCLIP_VARS, PG_VARS, PAPERCLIP_DEPLOY  # noqa: E402

WORKSPACE = "d10da65a-297f-4ba4-8cef-2fa9bb45fdef"  # My Projects (Auromations billing unpaid 2026-09-26; template still minted into Auromations)
q = rw.gql

project = q("""mutation($input: ProjectCreateInput!) {
  projectCreate(input: $input) { id environments { edges { node { id name } } } } }""",
  {"input": {"name": "paperclip-source", "workspaceId": WORKSPACE}})["projectCreate"]
pid = project["id"]
env = next(e["node"]["id"] for e in project["environments"]["edges"] if e["node"]["name"] == "production")
print(f"project {pid} env {env}", flush=True)


def create_service(name, image, variables):
    svc = q("""mutation($input: ServiceCreateInput!) { serviceCreate(input: $input) { id } }""",
      {"input": {"projectId": pid, "environmentId": env, "name": name,
                 "source": {"image": image}, "variables": variables}})["serviceCreate"]["id"]
    print(f"service {name} {svc}", flush=True)
    return svc


def volume(svc, path):
    q("""mutation($input: VolumeCreateInput!) { volumeCreate(input: $input) { id } }""",
      {"input": {"projectId": pid, "environmentId": env, "serviceId": svc, "mountPath": path}})


def instance(svc, patch):
    q("""mutation($s: String!, $e: String!, $input: ServiceInstanceUpdateInput!) {
      serviceInstanceUpdate(serviceId: $s, environmentId: $e, input: $input) }""",
      {"s": svc, "e": env, "input": patch})


pg = create_service("Postgres", PG_IMAGE, PG_VARS)
volume(pg, "/var/lib/postgresql/data")

app = create_service("Paperclip", IMAGE, PAPERCLIP_VARS)
volume(app, "/paperclip")
instance(app, PAPERCLIP_DEPLOY)
domain = q("""mutation($input: ServiceDomainCreateInput!) { serviceDomainCreate(input: $input) { domain } }""",
  {"input": {"environmentId": env, "serviceId": app, "targetPort": 3100}})["serviceDomainCreate"]["domain"]

# Fresh deploys after the domain exists (never `railway redeploy`: stale snapshots).
for svc in (pg, app):
    q("""mutation($s: String!, $e: String!) { serviceInstanceDeployV2(serviceId: $s, environmentId: $e) }""",
      {"s": svc, "e": env})
print(f"PROJECT={pid}\nENV={env}\nPG={pg}\nAPP={app}\nURL=https://{domain}")
