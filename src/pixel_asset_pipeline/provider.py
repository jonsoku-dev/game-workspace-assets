"""Generate a draft through the locally authenticated Codex image tool."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from uuid import UUID

from PIL import Image


def generate(prompt: str, destination: Path, references: tuple[Path, ...] = ()) -> None:
    """Write one fresh native image to an unused private staging path.

    Codex 0.165 omits image extension items from exec JSON output. Its native
    image directory is therefore selected only by this invocation's thread ID.
    """
    if not prompt.strip():
        raise ValueError("generation prompt must not be empty")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("generation staging destination already exists")
    for reference in references:
        if not reference.is_file():
            raise ValueError("reference must be an image file")
        with Image.open(reference) as image:
            image.verify()
    executable = shutil.which("codex")
    if executable is None:
        raise RuntimeError("Codex CLI is unavailable; install it and sign in with ChatGPT")
    # Do not inherit API credentials, proxy settings, or alternate model-service URLs.
    env = {key: os.environ[key] for key in (
        "HOME", "PATH", "CODEX_HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP",
        "SystemRoot", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    ) if key in os.environ}
    codex_home = Path(env.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    instruction = (
        "Generate exactly one PNG using ONLY the built-in image_gen tool. "
        "Use transparent_background=true. Do not execute commands, write code, "
        "use other tools, or fall back to an API or drawing. "
        "If the tool is unavailable, stop. "
    )
    instruction += "\nAsset request:\n" + prompt
    with tempfile.TemporaryDirectory(prefix="pixel-codex-") as work, tempfile.TemporaryFile() as events:
        # Ignore custom providers, MCP servers and hooks for this image-only run.
        command = [executable, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                   "--ignore-user-config", "--sandbox", "read-only", "-C", work,
                   "-c", 'forced_login_method="chatgpt"',
                   "-c", 'web_search="disabled"']
        for feature in ("shell_tool", "unified_exec", "apps", "plugins", "hooks", "multi_agent", "multi_agent_v2"):
            command.extend(["--disable", feature])
        for reference in references:
            command.extend(["--image", str(reference.resolve())])
        command.append("-")
        started = time.time_ns()
        try:
            result = subprocess.run(command, input=instruction.encode(), stdout=events,
                                    stderr=subprocess.DEVNULL, env=env, timeout=600,
                                    check=False)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Codex image generation timed out after 600 seconds") from None
        except OSError:
            raise RuntimeError("Codex CLI could not start") from None
        if result.returncode:
            raise RuntimeError(f"Codex image generation failed (exit {result.returncode}); check ChatGPT login and image-tool availability")
        events.seek(0)
        threads = []
        completed = False
        try:
            for line in events:
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("event must be an object")
                if event.get("type") == "thread.started":
                    threads.append(str(UUID(event["thread_id"])))
                if event.get("type") in {"turn.failed", "error"}:
                    raise RuntimeError("Codex image generation reported a failed turn")
                completed |= event.get("type") == "turn.completed"
        except (ValueError, KeyError, TypeError):
            raise RuntimeError("Codex returned an invalid generation event stream") from None
        if len(threads) != 1 or not completed:
            raise RuntimeError("Codex did not complete a uniquely identified image generation")
        folder = codex_home / "generated_images" / threads[0]
        if folder.is_symlink() or folder.resolve() != folder:
            raise RuntimeError("Codex image output directory is unsafe")
        candidates = list(folder.glob("*.png"))
        if len(candidates) != 1:
            raise RuntimeError("Codex did not produce exactly one image for this run")
        source = candidates[0]
        if source.is_symlink() or not source.is_file() or source.stat().st_mtime_ns < started:
            raise RuntimeError("Codex image output is stale or unsafe")
        if source.stat().st_size > 32 * 1024 * 1024:
            raise RuntimeError("Codex image exceeds the 32 MiB transport limit")
        try:
            with Image.open(source) as image:
                if image.format != "PNG":
                    raise ValueError("not PNG")
                image.verify()
        except (OSError, ValueError):
            raise RuntimeError("Codex produced an invalid PNG") from None
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as original:
            shutil.copyfileobj(original, output)
