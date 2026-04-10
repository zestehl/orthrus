"""Vendored UUID7 implementation.

UUID7 embeds a 48-bit Unix millisecond timestamp in the first 6 bytes,
making IDs lexicographically sortable by time. No external dependencies.

Spec: https://www.ietf.org/archive/id/draft-peabody-dispatch-new-uuid-format-01.html
"""

from __future__ import annotations

import re
import secrets
import struct
import time

_UUID7_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def generate_uuid7() -> str:
    """Generate a UUID7 string with embedded millisecond timestamp.

    Returns:
        Lowercase UUID7 string, e.g. '018f1234-5678-7abc-8def-0123456789ab'.
    """
    # 48-bit millisecond timestamp
    timestamp_ms = time.time_ns() // 1_000_000
    ts_bytes = struct.pack(">Q", timestamp_ms)  # 8 bytes, big-endian
    # We only need the lower 6 bytes (48 bits)
    ts_6 = ts_bytes[2:]

    # 80 bits of randomness (10 bytes)
    rand_bytes = secrets.token_bytes(10)

    # Assemble 16 bytes:
    # bytes 0-5: timestamp
    # byte 6: version (high nibble = 0x7) | random (low nibble)
    # byte 7: random
    # byte 8: variant (high 2 bits = 0b10) | random (low 6 bits)
    # bytes 9-15: random
    raw = bytearray(16)
    raw[0:6] = ts_6
    raw[6] = 0x70 | (rand_bytes[0] & 0x0F)  # version 7
    raw[7] = rand_bytes[1]
    raw[8] = 0x80 | (rand_bytes[2] & 0x3F)  # variant 0b10
    raw[9:16] = rand_bytes[3:10]

    # Format as standard UUID
    hex_str = raw.hex()
    return f"{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"


def parse_uuid7(uuid_str: str) -> tuple[int, bytes]:
    """Parse a UUID7 string into its components.

    Args:
        uuid_str: A valid UUID7 string.

    Returns:
        Tuple of (timestamp_ms, random_bytes).

    Raises:
        ValueError: If the string is not a valid UUID7.
    """
    if not isinstance(uuid_str, str):
        raise ValueError(f"Expected str, got {type(uuid_str).__name__}")

    if not _UUID7_PATTERN.match(uuid_str):
        raise ValueError(f"Invalid UUID7: {uuid_str!r}")

    # Strip dashes, decode hex
    hex_str = uuid_str.replace("-", "")
    raw = bytes.fromhex(hex_str)

    # Extract timestamp (bytes 0-5, big-endian → pad to 8 bytes)
    ts_bytes = b"\x00\x00" + raw[0:6]
    timestamp_ms = struct.unpack(">Q", ts_bytes)[0]

    # Extract random bytes
    rand_bytes = (
        bytes([raw[6] & 0x0F])  # low nibble of version byte
        + bytes([raw[7]])
        + bytes([raw[8] & 0x3F])  # low 6 bits of variant byte
        + raw[9:16]
    )

    return timestamp_ms, rand_bytes
