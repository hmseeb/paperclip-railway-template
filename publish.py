#!/usr/bin/env python3
"""Publish once, after the user confirms. The slug is minted from the template
name at first publish and never moves, so repair.py must already have saved
NAME. The icon goes through templateUpsertSettings, which does not re-mint it.

Usage: publish.py <templateId>
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path("~/.claude/skills/create-template-for-railway/scripts").expanduser()))
import rw  # noqa: E402
from repair import ICONS, NAME, WORKSPACE
ICON = ICONS["Paperclip"]  # noqa: E402

CATEGORY = "AI/ML"
DESCRIPTION = "Run AI agent teams (Claude Code, Codex, Gemini) with budgets and approvals"
assert len(DESCRIPTION) <= 75, len(DESCRIPTION)
assert "\u2014" not in DESCRIPTION

template_id = sys.argv[1]
readme = pathlib.Path(__file__).with_name("TEMPLATE_OVERVIEW.md").read_text()
assert "\u2014" not in readme
published = rw.gql(
    """mutation($id: String!, $input: TemplatePublishInput!) {
         templatePublish(id: $id, input: $input) { id code name isApproved } }""",
    {"id": template_id, "input": {"category": CATEGORY, "description": DESCRIPTION,
                                  "readme": readme, "workspaceId": WORKSPACE}},
)["templatePublish"]
print("published", published)
rw.gql(
    """mutation($id: String!, $input: TemplateUpsertSettingsInput!) {
         templateUpsertSettings(id: $id, input: $input) { id code image } }""",
    {"id": template_id, "input": {"workspaceId": WORKSPACE, "name": NAME, "image": ICON,
                                  "description": DESCRIPTION}},
    internal=True,
)
print(f"icon set\nhttps://railway.com/deploy/{published['code']}")
