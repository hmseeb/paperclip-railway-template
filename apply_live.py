#!/usr/bin/env python3
"""Re-applies spec.py to the live source Paperclip service and fresh-deploys it."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402
from spec import PAPERCLIP_VARS, PAPERCLIP_DEPLOY  # noqa: E402
PID, ENV, APP = "a351c29a-41e6-422d-be6e-566b094b4f02", "5dc1be1d-6d44-45c5-aa3c-68a6de6d789b", "d0ea2776-b502-4a7e-9197-27db0aa3f4b2"
rw.gql("""mutation($i: VariableCollectionUpsertInput!) { variableCollectionUpsert(input: $i) }""",
  {"i": {"projectId": PID, "environmentId": ENV, "serviceId": APP, "variables": PAPERCLIP_VARS, "skipDeploys": True}})
for gone in ("HOST", "BOOTSTRAP_CLI_CONFIG"):  # dropped from spec; ignore if already absent
    try:
        rw.gql("""mutation($i: VariableDeleteInput!) { variableDelete(input: $i) }""",
          {"i": {"projectId": PID, "environmentId": ENV, "serviceId": APP, "name": gone}})
    except RuntimeError:
        pass
rw.gql("""mutation($s: String!, $e: String!, $i: ServiceInstanceUpdateInput!) {
  serviceInstanceUpdate(serviceId: $s, environmentId: $e, input: $i) }""", {"s": APP, "e": ENV, "i": {k: ("" if v is None else v) for k, v in PAPERCLIP_DEPLOY.items()}})  # "" clears; null does not
print(rw.gql("""mutation($s: String!, $e: String!) { serviceInstanceDeployV2(serviceId: $s, environmentId: $e) }""",
  {"s": APP, "e": ENV}))
