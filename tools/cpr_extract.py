"""Minimal reader for ASCARON_ARCHIVE V0.9 (.cpr) files used by Port Royale 2.

Format (little-endian, documented at http://wiki.xentax.com/index.php?title=Patrician):

    Header (32 bytes):
      char[16] "ASCARON_ARCHIVE "
      char[4]  "V0.9"
      byte[12] null padding

    One or more index blocks, each:
      uint32 index_size           total bytes of this block (header + entries)
      uint32 dir_size             entries section size (= index_size - 16)
      uint32 num_files            number of entries
      uint32 next_index_relpos    where the next index block starts, relative
                                  to the end of this header (0 = no more)
      For each file entry:
        uint32 data_offset        absolute offset of file payload in the .cpr
        uint32 raw_length         payload length
        uint32 unknown            (always 1 in the samples we've seen)
        char[]  filename          null-terminated, ISO-8859-1 encoded,
                                  uses '\\' as path separator

Commands:
  list <file.cpr>                    Print "<size> <offset>  <path>" lines.
  extract <file.cpr> <out_dir> [glob...]
                                      Extract entries whose path matches any of
                                      the given glob patterns (case-insensitive).
                                      With no patterns extracts everything.
"""

from __future__ import annotations

import fnmatch
import os
import struct
import sys
from pathlib import Path

MAGIC = b"ASCARON_ARCHIVE V0.9"
HEADER_LEN = 32
INDEX_HDR_LEN = 16


def parse_index(f) -> list[tuple[str, int, int]]:
    head = f.read(HEADER_LEN)
    if head[:20] != MAGIC:
        raise ValueError("not an ASCARON_ARCHIVE V0.9 file")
    entries: list[tuple[str, int, int]] = []
    block_pos = f.tell()
    while True:
        hdr = f.read(INDEX_HDR_LEN)
        if not hdr:
            break
        if len(hdr) < INDEX_HDR_LEN:
            raise ValueError(f"truncated index header at {block_pos}")
        index_size, dir_size, num_files, next_rel = struct.unpack("<4I", hdr)
        if dir_size > index_size:
            raise ValueError("dir_size > index_size")
        if num_files * 13 > dir_size:
            raise ValueError("num_files too large for dir_size")
        data = f.read(dir_size - INDEX_HDR_LEN)
        if len(data) < dir_size - INDEX_HDR_LEN:
            raise ValueError("truncated index block")
        pos = 0
        for _ in range(num_files):
            if pos + 12 > len(data):
                raise ValueError("entry header overruns block")
            off, size, _u = struct.unpack_from("<3I", data, pos)
            pos += 12
            end = data.find(b"\x00", pos)
            if end < 0:
                raise ValueError("unterminated filename")
            name = data[pos:end].decode("iso-8859-1")
            entries.append((name, off, size))
            pos = end + 1
        if next_rel == 0:
            break
        block_pos += index_size + next_rel
        f.seek(block_pos, 0)
    return entries


def cmd_list(path: str):
    with open(path, "rb") as f:
        idx = parse_index(f)
    print(f"# {len(idx)} entries in {path}")
    for name, off, size in idx:
        print(f"{size:>10}  {off:>10}  {name}")


def cmd_extract(path: str, out_dir: str, patterns: list[str]):
    pats = [p.lower() for p in patterns] if patterns else None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(path, "rb") as f:
        idx = parse_index(f)
        n_out = 0
        for name, off, size in idx:
            lname = name.lower()
            if pats and not any(fnmatch.fnmatch(lname, p) for p in pats):
                continue
            rel = name.replace("\\", os.sep)
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            f.seek(off, 0)
            dest.write_bytes(f.read(size))
            n_out += 1
            print(f"extracted: {name} ({size} bytes)")
    print(f"# {n_out} files extracted to {out}")


def main(argv: list[str]):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    cmd = argv[1]
    if cmd == "list" and len(argv) == 3:
        cmd_list(argv[2])
    elif cmd == "extract" and len(argv) >= 4:
        cmd_extract(argv[2], argv[3], argv[4:])
    else:
        print(__doc__, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
