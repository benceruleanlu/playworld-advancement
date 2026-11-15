"""Describe only this GC chunk's camera command; never inspect future actions."""
from . import poses as P, session as S

MOTION = {"j": "pans left", "l": "pans right", "i": "tilts up", "k": "tilts down",
          "w": "moves forward", "s": "moves backward", "a": "moves left", "d": "moves right",
          "none": "remains stationary"}


def compose(caption, name, action):
    parsed = S.parse_chunk_name(name)
    if not parsed or not parsed[0].startswith("GC"):
        return caption
    keys = {k.lower() for k in P.parse_action(action)}
    if len(keys) != 1 or not keys <= MOTION.keys():
        return caption
    return f"{caption}\nDuring this segment, the camera {MOTION[keys.pop()]}."
