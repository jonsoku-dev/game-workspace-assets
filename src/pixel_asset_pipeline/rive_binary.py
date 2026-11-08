"""Write embedded PNG pose animations in the public Rive runtime format.

Independent encoder based on the MIT-licensed rive-app/rive-runtime schema,
revision 9afebeb046659cc3ffed906825023012e4d3cd48 (include/rive/generated),
runtime_header.hpp and src/core/binary_writer.cpp. No editor or cloud service.
The numeric input selects animations by their zero-based supplied order.
Non-looping animations hold their final pose until another action is selected.
"""

from collections.abc import Sequence
from io import BytesIO
import struct

from PIL import Image


Frame = tuple[bytes, int]
Animation = tuple[str, bool, Sequence[Frame]]


def _uint(value: int) -> bytes:
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def _blob(value: bytes) -> bytes:
    return _uint(len(value)) + value


def _object(type_id: int, *properties: tuple[int, bytes]) -> bytes:
    return _uint(type_id) + b"".join(_uint(key) + value for key, value in properties) + b"\0"


def _float(value: float) -> bytes:
    return struct.pack("<f", value)


def bake(
    width: int,
    height: int,
    animations: Sequence[Animation],
    *,
    artboard: str = "Character",
    machine: str = "Character Actions",
    input_name: str = "action",
) -> bytes:
    """Encode ordered ``(name, loop, [(png_bytes, duration_ms), ...])`` actions.

    Durations must be positive integer milliseconds. A 1000 fps timeline stores
    every supplied duration without rounding. Each action is limited to 2**24
    milliseconds so frame integers stay exactly representable by runtime floats.
    PNGs must have exactly the artboard dimensions. Identical PNG bytes share an
    embedded asset and image node. Numeric input values outside the supplied
    action indices leave the current state unchanged.
    """
    if any(type(value) is not int or not 0 < value <= 16384 for value in (width, height)):
        raise ValueError("width and height must be integers in 1..16384")
    if not animations:
        raise ValueError("at least one animation is required")
    if any(not isinstance(name, str) or not name.strip() for name in (artboard, machine, input_name)):
        raise ValueError("artboard, machine and input names must be nonempty")

    assets: dict[bytes, int] = {}
    timelines: list[tuple[str, bool, list[tuple[int, int]], int]] = []
    names: set[str] = set()
    for name, loop, frames in animations:
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("animation names must be nonempty and unique")
        if type(loop) is not bool or not frames:
            raise ValueError("each animation requires a boolean loop and at least one frame")
        names.add(name)
        timeline = []
        elapsed = 0
        for png, duration in frames:
            if type(duration) is not int or duration <= 0:
                raise ValueError("frame durations must be positive integer milliseconds")
            if not isinstance(png, bytes):
                raise ValueError("frame images must be PNG bytes")
            if png not in assets:
                try:
                    with Image.open(BytesIO(png)) as image:
                        if image.format != "PNG" or image.size != (width, height):
                            raise ValueError("PNG dimensions must match the artboard")
                        image.load()
                except (OSError, SyntaxError) as error:
                    raise ValueError("invalid PNG frame") from error
                assets[png] = len(assets)
            timeline.append((assets[png], elapsed))
            elapsed += duration
        if elapsed > 2**24:
            raise ValueError("animation duration exceeds 2**24 milliseconds")
        timelines.append((name, loop, timeline, elapsed))

    # All keys are in the runtime schema, so the unknown-property table is empty.
    chunks = [b"RIVE" + _uint(7) + _uint(0) + _uint(0) + _uint(0), _object(23)]
    for png, index in assets.items():
        chunks.append(_object(105, (203, _blob(f"pose-{index}.png".encode())),
                              (204, _uint(index)), (207, _float(height)), (208, _float(width))))
        chunks.append(_object(106, (212, _blob(png))))
    chunks.append(_object(1, (4, _blob(artboard.encode())), (7, _float(width)),
                          (8, _float(height)), (236, _uint(0))))
    first = timelines[0][2][0][0]
    for index in assets.values():
        chunks.append(_object(100, (4, _blob(f"pose-{index}".encode())), (5, _uint(0)),
                              (206, _uint(index)), (380, _float(0)), (381, _float(0)),
                              (18, _float(float(index == first)))))

    for name, loop, timeline, duration in timelines:
        chunks.append(_object(31, (55, _blob(name.encode())), (56, _uint(1000)),
                              (57, _uint(duration)), (59, _uint(int(loop)))))
        keys = [{0: 0.0} for _ in assets]
        previous = None
        for index, time in timeline:
            if index != previous:
                if previous is not None:
                    keys[previous][time] = 0.0
                keys[index][time] = 1.0
                previous = index
        for index, values in enumerate(keys):
            chunks.append(_object(25, (51, _uint(index + 1))))
            chunks.append(_object(26, (53, _uint(18))))
            for time, opacity in sorted(values.items()):
                # Interpolation 0 is hold, preventing cross-fades between poses.
                chunks.append(_object(30, (67, _uint(time)), (68, _uint(0)), (70, _float(opacity))))

    chunks.append(_object(53, (55, _blob(machine.encode()))))
    chunks.append(_object(56, (138, _blob(input_name.encode())), (140, _float(0))))
    chunks.append(_object(57, (138, _blob(b"Actions"))))
    # Layer state indices are Entry=0, Any=1, Exit=2, then animation states.
    chunks.append(_object(63))
    chunks.append(_object(65, (151, _uint(3))))
    chunks.append(_object(62))
    for index in range(len(timelines)):
        chunks.append(_object(65, (151, _uint(index + 3))))
        chunks.append(_object(70, (155, _uint(0)), (156, _uint(0)), (157, _float(index))))
    chunks.append(_object(64))
    for index in range(len(timelines)):
        chunks.append(_object(61, (149, _uint(index))))
    return b"".join(chunks)
