#!/usr/bin/env python3
"""Puts back everything templateGenerate strips and writes the template into Auromations.

The source project lives in My Projects (Auromations billing was UNPAID on 2026-09-26, so
it could not create projects), but templateUpsertConfig takes any workspaceId, so the
template itself is minted directly in Auromations with fresh service/volume UUIDs.

Usage: repair.py <templateId|new> [generated.json]
"""
import json, pathlib, sys, uuid
sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402
from spec import PAPERCLIP_VARS, PG_VARS, PAPERCLIP_DEPLOY  # noqa: E402

WORKSPACE = "fc4796db-2c6c-4354-a564-d4a1d900af53"  # Auromations
NAME = "Paperclip (Official Image)"
ICONS = {
    # 512px PNG pinned to the release tag, verified image/png.
    "Paperclip": "https://raw.githubusercontent.com/paperclipai/paperclip/v2026.916.1/ui/public/android-chrome-512x512.png",
    "Postgres": "https://devicons.railway.app/i/postgresql.svg",
}
DESCRIPTIONS = {
    "PAPERCLIP_DEPLOYMENT_EXPOSURE": "private: sign-in required; the first signed-in user claims admin from the browser. Claim right after deploy.",
    "PAPERCLIP_PUBLIC_URL": "Canonical URL used for auth callbacks and invite links. Change it if you add a custom domain.",
}


def as_vars(values):
    return {k: {"defaultValue": v, "isOptional": False, **({"description": DESCRIPTIONS[k]} if k in DESCRIPTIONS else {})}
            for k, v in values.items()}


VARIABLES = {"Paperclip": as_vars(PAPERCLIP_VARS), "Postgres": as_vars(PG_VARS)}
DEPLOY = {"Paperclip": PAPERCLIP_DEPLOY}


def main():
    template_id = sys.argv[1]
    config = json.loads(pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "generated.json").read_text())
    config = config.get("templateGenerate", config)
    config = config.get("serializedConfig", config)
    if template_id != "new":
        # Updating: start from the template's own config; the generated one carries source
        # service ids, which the server rejects as "ID collision".
        config = rw.gql("query($id: String!) { template(id: $id) { serializedConfig } }",
                        {"id": template_id})["template"]["serializedConfig"]
    else:
        template_id = str(uuid.uuid4())
        remap = {sid: str(uuid.uuid4()) for sid in config["services"]}
        services = {}
        for sid, svc in config["services"].items():
            svc = json.loads(json.dumps(svc))
            svc["volumeMounts"] = {remap.get(k, k): v for k, v in svc.get("volumeMounts", {}).items()}
            services[remap[sid]] = svc
        config = {"buckets": config.get("buckets", {}), "services": services}
        print("minting template", template_id)
    for svc in config["services"].values():
        name = svc["name"]
        svc["variables"] = VARIABLES[name]
        svc["icon"] = ICONS[name]
        svc.setdefault("deploy", {}).update({k: v for k, v in DEPLOY.get(name, {}).items()})
    saved = rw.gql("""mutation($id: String!, $input: TemplateUpsertConfigInput!) {
        templateUpsertConfig(id: $id, input: $input) { id code } }""",
        {"id": template_id, "input": {"name": NAME, "workspaceId": WORKSPACE,
                                      "serializedConfig": config, "canvasConfig": {}}},
        internal=True)["templateUpsertConfig"]
    print(f"saved id {saved['id']} code {saved['code']}")

    back = rw.gql("query($c: String!) { template(code: $c) { teamId serializedConfig } }", {"c": saved["code"]})["template"]
    cfg = back["serializedConfig"]
    cfg = json.loads(cfg) if isinstance(cfg, str) else cfg
    problems = []
    for svc in cfg["services"].values():
        name = svc["name"]
        got = svc.get("variables", {})
        for key, want in VARIABLES[name].items():
            if got.get(key, {}).get("defaultValue") != want["defaultValue"]:
                problems.append(f"{name}.{key}: {got.get(key, {}).get('defaultValue')!r}")
        for key, val in DEPLOY.get(name, {}).items():
            if svc.get("deploy", {}).get(key) != val:
                problems.append(f"{name}.deploy.{key}: {svc.get('deploy', {}).get(key)!r}")
        if svc.get("icon") != ICONS[name]:
            problems.append(f"{name}.icon")
        if name == "Paperclip" and "3100" not in json.dumps(svc.get("networking")):
            problems.append("Paperclip domain target port")
    print("workspace:", back.get("teamId"))
    if problems:
        print("PROBLEMS:", *problems, sep="\n - ")
        sys.exit(1)
    print("read-back clean:", saved["code"])


if __name__ == "__main__":
    main()
