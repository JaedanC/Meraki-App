import hashlib
import json

import pygui_cython as pygui


def _deterministic_hash(obj: dict | list | str, seed=""):
    """
    Calculates a deterministic integer hash of a string or JSON-serializable Python object.
    """
    if isinstance(obj, str):
        # Encode the string to bytes
        obj_bytes = (seed + obj).encode('utf-8')
    else:
        try:
            # Serialize the object to a consistently ordered JSON string
            obj_bytes = (json.dumps(obj, sort_keys=True) + seed).encode('utf-8')
        except (TypeError, ValueError) as e:
            raise TypeError("Object of type %s is not JSON-serializable" % type(obj).__name__) from e

    # Apply SHA-256 hash
    hasher = hashlib.sha256()
    hasher.update(obj_bytes)
    digest = hasher.digest()

    # Convert the hash digest to an integer
    return int.from_bytes(digest, byteorder='big')


def hex_to_u32(hex_string: str) -> int:
    h = hex_string.lstrip("#")
    return pygui.color_convert_float4_to_u32(tuple([int(h[i:i+2], 16) / 255 for i in (0, 2, 4)] + [1]))


def hex_to_vec4(hex_string: str) -> pygui.Vec4:
    h = hex_string.lstrip("#")
    return pygui.Vec4.zero().from_tuple([int(h[i:i+2], 16) / 255 for i in (0, 2, 4)] + [1])


class Colour:
    seed = pygui.Int(12394)
    colours = [
        hex_to_vec4("#264653"),
        hex_to_vec4("#2a9d8f"),
        hex_to_vec4("#e9c46a"),
        hex_to_vec4("#f4a261"),
        hex_to_vec4("#e76f51"),
        hex_to_vec4("#240046"),
        hex_to_vec4("#3c096c"),
        hex_to_vec4("#5a189a"),
        hex_to_vec4("#7b2cbf"),
        hex_to_vec4("#1b4332"),
        hex_to_vec4("#2D6A4F"),
        hex_to_vec4("#40916C"),
        hex_to_vec4("#540804"),
        hex_to_vec4("#81171b"),
        hex_to_vec4("#ad2e24"),
        hex_to_vec4("#c75146"),
    ]

    @staticmethod
    def get_colour(for_obj:  dict | list | str) -> pygui.Vec4:
        idx = _deterministic_hash(for_obj, seed=str(Colour.seed.value))
        return Colour.colours[idx % len(Colour.colours)]
