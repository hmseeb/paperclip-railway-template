#!/usr/bin/env python3
"""Start command must launch what the image itself launches.

Usage: spec_test.py [upstream-Dockerfile]. Without an argument it fetches, with `gh api`, the
Dockerfile of the release spec.IMAGE is pinned to. To bump: set IMAGE to the new release tag,
run this test against it (it fails until the start command and env match), then test-deploy.
"""
import json, pathlib, re, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import spec  # noqa: E402

if len(sys.argv) > 1:
    dockerfile = pathlib.Path(sys.argv[1]).read_text()
else:
    tag = "v" + spec.IMAGE.rsplit(":", 1)[1]
    dockerfile = subprocess.check_output(["gh", "api", "-H", "Accept: application/vnd.github.raw",
                                          f"repos/paperclipai/paperclip/contents/Dockerfile?ref={tag}"], text=True)

entrypoint = json.loads(re.search(r"^ENTRYPOINT (\[.*\])$", dockerfile, re.M).group(1))
cmd = json.loads(re.search(r"^CMD (\[.*\])$", dockerfile, re.M).group(1))
fails = []
if not spec.START_COMMAND.startswith(" ".join(entrypoint) + " "):
    fails.append(f"entrypoint: start command does not begin with {' '.join(entrypoint)!r}")
want_exec = "exec " + " ".join([cmd[0], "--import", "/tmp/usage-patch.mjs", *cmd[1:]]) + '"'
if not spec.START_COMMAND.endswith(want_exec):
    fails.append(f"cmd: start command does not end with {want_exec!r}")
# Pinned, never floating: the start command and env above depend on image internals that
# change between releases (2026.1117.0 alone moved CMD, tini flags and the provider check).
if not re.fullmatch(r"ghcr\.io/paperclipai/paperclip:\d{4}\.\d+\.\d+", spec.IMAGE):
    fails.append(f"image: {spec.IMAGE} is not pinned to a release tag")
if "latest" in getattr(spec, "ICON_REF", "latest"):
    fails.append("icon must be pinned to a real git ref")
# Since 2026.1106.0 agents default to the Paperclip Runner, whose session.open verifies the
# installed provider files: a symlink over a bundled binary fails it (admission_installation).
if re.search(r"ln -sf [^;]* /app/node_modules|ln -sf /tmp/\S+-launcher \$f", spec.START_COMMAND):
    fails.append("start command must not replace binaries inside the image's node_modules")
# Upstream bug paperclipai/paperclip#18557: unset, the server verifies ACPX packages against
# /app/server, which the pnpm image layout cannot pass, so every new Runner agent stays verifying.
pack = re.search(r"PAPERCLIP_RUNNER_REMOTE_PROVIDER_PACK_PATH=(\S+)", dockerfile)
want_root = pack.group(1) if pack else None
if spec.PAPERCLIP_VARS.get("PAPERCLIP_ACPX_PROVIDER_PACKAGE_ROOT") != want_root:
    fails.append(f"PAPERCLIP_ACPX_PROVIDER_PACKAGE_ROOT must be the image's provider pack {want_root!r}")
for f in fails:
    print("FAIL", f)
print("PASS" if not fails else f"{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
