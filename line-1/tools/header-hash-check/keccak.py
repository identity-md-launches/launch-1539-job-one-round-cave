"""Pure Ethereum Keccak-256, copied from the reviewed Line 3 implementation."""
MASK64 = (1 << 64) - 1
ROTATIONS = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)
ROUND_CONSTANTS = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
    0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
    0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
    0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
    0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
    0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)


def rotate_left(value, bits):
    return ((value << bits) | (value >> (64 - bits))) & MASK64 if bits else value


def keccak_f1600(state):
    """Apply 24 Keccak-f[1600] rounds to 25 little-endian 64-bit lanes."""
    for constant in ROUND_CONSTANTS:
        columns = [0] * 5
        for x in range(5):
            columns[x] = (state[x] ^ state[x + 5] ^ state[x + 10] ^
                          state[x + 15] ^ state[x + 20])
        for x in range(5):
            delta = columns[(x - 1) % 5] ^ rotate_left(columns[(x + 1) % 5], 1)
            for y in range(5):
                state[x + 5 * y] ^= delta

        moved = [0] * 25
        for x in range(5):
            for y in range(5):
                moved[y + 5 * ((2 * x + 3 * y) % 5)] = rotate_left(
                    state[x + 5 * y], ROTATIONS[x][y])
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] = (moved[x + 5 * y] ^
                                    ((~moved[(x + 1) % 5 + 5 * y]) &
                                     moved[(x + 2) % 5 + 5 * y])) & MASK64
        state[0] ^= constant


def keccak256(data):
    """Ethereum Keccak-256, with Keccak's 0x01 suffix (not SHA3's 0x06)."""
    if not isinstance(data, bytes):
        raise TypeError("Keccak input must be bytes")
    rate = 136
    padding_length = rate - len(data) % rate
    padded = data + b"\x01" + b"\x00" * (padding_length - 1)
    padded = padded[:-1] + bytes([padded[-1] | 0x80])
    state = [0] * 25
    for offset in range(0, len(padded), rate):
        block = padded[offset:offset + rate]
        for lane in range(rate // 8):
            state[lane] ^= int.from_bytes(block[8 * lane:8 * lane + 8], "little")
        keccak_f1600(state)
    return b"".join(lane.to_bytes(8, "little") for lane in state)[:32]

