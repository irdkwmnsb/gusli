import io
import pathlib
from typing import IO

CHUNK_SIZE = 65536


def copy_buffer(in_buf: IO, out_buf: IO):
    while True:
        d = in_buf.read(CHUNK_SIZE)
        if d == b"":
            break
        out_buf.write(d)


def save_to_disk(buf: IO, path: pathlib.Path):
    with path.open("wb") as o_buf:
        copy_buffer(buf, o_buf)
