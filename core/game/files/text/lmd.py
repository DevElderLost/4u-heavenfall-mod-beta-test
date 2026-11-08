"""MH4U LMD text files (ARC type 0x62440501, magic "lmd\\0"): read, write back byte for byte, add messages.

Layout:

    0x00  "lmd\\0"
    0x04  u32 version (0x1010B in every file of the game)
    0x08  u32 message count: the game asks for a message by its index here
    0x0C  u32 node count
    0x10  u32 string count
    0x14  u32 offset of the labels: per message (u32 hash, u32 flag << 22 | first node)
    0x18  u32 offset of the nodes, 16 bytes each (u32 kind, u32 value, 2 x u32 0): kind 1 shows string `value`,
          22 ends the message, 2 is a number filled in by the game, 5 / 0x40000005 start / end a colour...
    0x1C  u32 offset of the string table: (u32 offset, u32 length, u32 length) per string; UTF-16LE text
          ending with a NUL. The two lengths are equal in most files.
    0x20  u32 offset of the file's name (ASCII, NUL-terminated, at a 4-byte boundary, at the end)

The game looks a message up by label index (FUN_00cdfa80: label -> first node -> its string). The bytes
between the string table and the name are kept as they are (strings are not always packed), so a file
written back without changes is identical.
"""

import struct
import zlib
from dataclasses import dataclass, field

LMD_TYPE_HASH = 0x62440501
MAGIC = b"lmd\0"
HEADER = 0x24
TEXT, END, NUMBER = 1, 22, 2
SLOT_NUMBER = 100  # a number node's value: the text renderer's string slot 0 (FUN_005a99a8)
SLOT_MARK = "{slot}"  # in a text given to add_message / set_message: a number node at that place
DEFAULT_FLAG = 1  # the label flag of most messages of the game


class LmdError(ValueError):
    pass


@dataclass
class Lmd:
    version: int
    labels: list[tuple[int, int]]                 # (hash, flag << 22 | first node)
    nodes: list[tuple[int, int, int, int]]
    entries: list[tuple[int, int, int]]           # string table as read: (offset, length, length)
    data: bytes                                   # everything between the string table and the name
    data_at: int                                  # file offset of `data`
    name: str
    added: list[str] = field(default_factory=list)  # strings of the added messages, after `data`

    @property
    def message_count(self) -> int:
        return len(self.labels)

    @property
    def strings(self) -> list[str]:
        return [self._string(i) for i in range(len(self.entries) + len(self.added))]

    def _string(self, index: int) -> str:
        if index >= len(self.entries):
            return self.added[index - len(self.entries)]
        offset, length, _ = self.entries[index]
        start = offset - self.data_at
        return self.data[start:start + 2 * length].decode("utf-16-le")

    def message(self, index: int) -> str:
        """The text of message `index`: its text nodes, in order (numbers and colours left out)."""
        node = self.labels[index][1] & 0x3FFFFF
        parts = []
        while node < len(self.nodes) and self.nodes[node][0] != END:
            kind, value = self.nodes[node][:2]
            if kind == TEXT:
                parts.append(self._string(value))
            node += 1
        return "".join(parts)

    def add_message(self, text: str) -> int:
        """Append a message showing `text`, SLOT_MARK being a number node there; returns its index."""
        index = self._add_label()
        self._add_nodes(text)
        return index

    def set_message(self, index: int, text: str) -> None:
        """Make message `index` show `text`, SLOT_MARK being a number node there. The label keeps its hash and flag and
        gets nodes of its own at the end (messages may share nodes), so what the old message held besides its text
        (numbers, colours) is dropped."""
        if not 0 <= index < len(self.labels):
            raise IndexError(f"the LMD has {len(self.labels)} messages, no {index}")
        hash_, flag = self.labels[index]
        self.labels[index] = (hash_, flag & ~0x3FFFFF | len(self.nodes))
        self._add_nodes(text)

    def _add_nodes(self, text: str) -> None:
        """The nodes of a message: a text node per part around the marks (a text without marks has exactly one, even
        empty), a number node at each mark, the end."""
        parts = text.split(SLOT_MARK)
        for position, part in enumerate(parts):
            if position > 0:
                self.nodes.append((NUMBER, SLOT_NUMBER, 0, 0))
            if part or len(parts) == 1:
                self.nodes.append((TEXT, len(self.entries) + len(self.added), 0, 0))
                self.added.append(part)
        self.nodes.append((END, 0, 0, 0))

    def add_number_message(self, value: int = SLOT_NUMBER) -> int:
        """Append a message showing only a number node: `value` 100 is the text renderer's string slot 0 (Common
        message 0 is that node, then "z": the money). Returns its index."""
        index = self._add_label()
        self.nodes.append((NUMBER, value, 0, 0))
        self.nodes.append((END, 0, 0, 0))
        return index

    def _add_label(self) -> int:
        index = len(self.labels)
        hashes = {h for h, _ in self.labels}
        label = zlib.crc32(f"{self.name}_layered_{index}".encode())
        while label in hashes:
            label = (label + 1) & 0xFFFFFFFF
        self.labels.append((label, DEFAULT_FLAG << 22 | len(self.nodes)))
        return index


def parse_lmd(data: bytes) -> Lmd:
    if data[:4] != MAGIC or len(data) < HEADER:
        raise LmdError("not an LMD file")
    version, labels, nodes, strings, labels_at, nodes_at, table_at, name_at = struct.unpack_from("<8I", data, 4)
    data_at = table_at + 12 * strings
    if (labels_at != HEADER or nodes_at != labels_at + 8 * labels or table_at != nodes_at + 16 * nodes
            or not data_at <= name_at < len(data)):
        raise LmdError("unexpected LMD layout")
    name = data[name_at:].split(b"\0", 1)[0]
    if name_at + len(name) + 1 != len(data):
        raise LmdError("unexpected bytes after the LMD's name")
    return Lmd(version,
               [struct.unpack_from("<II", data, labels_at + 8 * i) for i in range(labels)],
               [struct.unpack_from("<4I", data, nodes_at + 16 * i) for i in range(nodes)],
               [struct.unpack_from("<3I", data, table_at + 12 * i) for i in range(strings)],
               data[data_at:name_at], data_at, name.decode("ascii"))


def write_lmd(lmd: Lmd) -> bytes:
    nodes_at = HEADER + 8 * len(lmd.labels)
    table_at = nodes_at + 16 * len(lmd.nodes)
    strings = len(lmd.entries) + len(lmd.added)
    data_at = table_at + 12 * strings
    shift = data_at - lmd.data_at
    entries = [(offset + shift, length, other) for offset, length, other in lmd.entries]
    data = bytearray(lmd.data)  # its length is a multiple of 4: the name was at a 4-byte boundary
    for text in lmd.added:
        entries.append((data_at + len(data), len(text), len(text)))
        data += text.encode("utf-16-le") + b"\0\0"
    data += bytes(-(data_at + len(data)) % 4)
    name_at = data_at + len(data)
    out = bytearray(MAGIC)
    out += struct.pack("<8I", lmd.version, len(lmd.labels), len(lmd.nodes), strings, HEADER, nodes_at, table_at,
                       name_at)
    for label in lmd.labels:
        out += struct.pack("<II", *label)
    for node in lmd.nodes:
        out += struct.pack("<4I", *node)
    for entry in entries:
        out += struct.pack("<3I", *entry)
    out += data + lmd.name.encode("ascii") + b"\0"
    return bytes(out)


# Strings by index, and rewriting some of them in place (a monster's name: `<lang>\msg\emName_<lang>` in
# `<lang>/data/core_common.arc`). Only the header's string count (0x10),
# string table (0x1C) and name offset (0x20) are read; the records before the string table are kept. The strings follow
# the table, each with its 0 and starting at a multiple of 4 (zeros between); the name follows them at a multiple
# of 4. Every LMD of the update keeps this layout (tests/game/files/test_lmd.py).
COUNT, TABLE, NAME = 0x10, 0x1C, 0x20


def _align(n: int) -> int:
    return n + -n % 4


def read_lmd(data: bytes) -> list[str]:
    """The strings of an LMD, by index."""
    if data[:4] != MAGIC:
        raise LmdError("not an LMD file")
    count, table = struct.unpack_from("<I", data, COUNT)[0], struct.unpack_from("<I", data, TABLE)[0]
    strings = []
    for i in range(count):
        offset, length, _ = struct.unpack_from("<3I", data, table + 12 * i)
        strings.append(data[offset:offset + 2 * length].decode("utf-16-le"))
    return strings


def with_strings(data: bytes, new: dict[int, str]) -> bytes:
    """The LMD `data` with the strings of `new` (index -> text) replaced, laid out again."""
    strings = read_lmd(data)
    for index, text in new.items():
        if not 0 <= index < len(strings):
            raise IndexError(f"the LMD has {len(strings)} strings, no {index}")
        strings[index] = text
    table = struct.unpack_from("<I", data, TABLE)[0]
    name = data[struct.unpack_from("<I", data, NAME)[0]:]
    out = bytearray(data[:table + 12 * len(strings)])
    for i, text in enumerate(strings):
        out += bytes(_align(len(out)) - len(out))
        struct.pack_into("<3I", out, table + 12 * i, len(out), len(text), len(text))
        out += text.encode("utf-16-le") + b"\0\0"
    out += bytes(_align(len(out)) - len(out))
    struct.pack_into("<I", out, NAME, len(out))
    return bytes(out + name)
