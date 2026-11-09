"""Local artifact I/O shared by the asset producers."""
import ctypes
import io
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from PIL import Image


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def local_path(root, value):
    """A request-relative input file that resolves inside the request directory (symlinks included)."""
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("source paths must be nonempty relative paths")
    path = (Path(root) / value).resolve(strict=True)
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise ValueError("source paths must stay within the request directory")
    if path.stat().st_size > 16_777_216:
        raise ValueError("source exceeds 16 MiB")
    return path


def read_once(path, cache, limit=16_777_216):
    """Bytes of `path`, read once per producer run so decoding, hashing and copying see the same bytes."""
    key = Path(path).resolve(strict=True)
    if key not in cache:
        with key.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError(f"{key.name} exceeds {limit} bytes")
        cache[key] = data
    return cache[key]


def png_bytes(data, max_pixels=16_777_216):
    return open_png(io.BytesIO(data), max_pixels)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


GIF_TICK_MS = 10
GIF_MIN_DELAY_MS = 20  # browsers clamp delays of 10ms or less to about 100ms


def gif_timeline(durations):
    """GIF delays for exact millisecond durations: (frame index, delay) pairs.

    Cumulative boundaries are rounded to the 10ms GIF tick, so rounding never drifts
    across a sequence. Any exposure that would be shorter than 20ms is merged into the
    previous emitted frame instead of being written as a 0/10ms delay.
    """
    total, edges = 0, [0]
    for duration in durations:
        total += duration
        edges.append(int((total + GIF_TICK_MS / 2) // GIF_TICK_MS * GIF_TICK_MS))
    out = []
    for index, (start, stop) in enumerate(zip(edges, edges[1:])):
        delay = stop - start
        if delay < GIF_MIN_DELAY_MS and out:
            out[-1][1] += delay
        else:
            out.append([index, delay])
    if len(out) > 1 and out[0][1] < GIF_MIN_DELAY_MS:
        out[1][1] += out[0][1]
        out.pop(0)
    return [(index, max(delay, GIF_MIN_DELAY_MS)) for index, delay in out]


def open_png(path, max_pixels=16_777_216):
    with Image.open(path, formats=["PNG"]) as source:
        if source.width * source.height > max_pixels or source.is_animated:
            raise ValueError(f"expected a static PNG of at most {max_pixels} pixels")
        source.load()
        return source.copy()


def publish(output: Path, producer, *inputs):
    if output.exists() or output.is_symlink():
        raise ValueError("output already exists; choose a new bundle path")
    output.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".pixel-build-") as temp:
        stage = Path(temp) / "bundle"
        stage.mkdir()
        files = producer(*inputs, stage)
        for filename in files.values():
            if Path(filename).name != filename or not (stage / filename).is_file():
                raise ValueError(f"missing or invalid bundle artifact: {filename}")
        if sys.platform == 'win32':
            stage.rename(output)
        else:
            libc = ctypes.CDLL(None, use_errno=True)
            if sys.platform == 'darwin':
                rename, flag = libc.renameatx_np, 0x4
            elif sys.platform.startswith('linux') and hasattr(libc, 'renameat2'):
                rename, flag = libc.renameat2, 1
            else:
                raise RuntimeError('This platform lacks atomic no-replace directory publication')
            rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            rename.restype = ctypes.c_int
            if rename(-1, os.fsencode(stage.absolute()), -1, os.fsencode(output.absolute()), flag):
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), str(output))
    return {"schema_version": 1, "status": "ready", "files": files}
