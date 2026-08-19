import os
import struct
import zlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import scheduler as sched
from routers import admin, auth, chat, chats, health, push, telegram, upload


def _make_png(width: int, height: int, r: int, g: int, b: int) -> bytes:
    """Generate a solid-color PNG without external libraries."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = bytes([0]) + bytes([r, g, b] * width)
    idat = zlib.compress(row * height)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def _make_ico(r: int, g: int, b: int) -> bytes:
    """Generate a 32x32 ICO file with an embedded PNG."""
    png = _make_png(32, 32, r, g, b)
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


@asynccontextmanager
async def lifespan(app: FastAPI):
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    icon_path = os.path.join(static_dir, "icon.png")
    if not os.path.exists(icon_path):
        png = _make_png(180, 180, 124, 58, 237)  # #7c3aed purple
        with open(icon_path, "wb") as f:
            f.write(png)
    favicon_path = os.path.join(static_dir, "favicon.ico")
    if not os.path.exists(favicon_path):
        with open(favicon_path, "wb") as f:
            f.write(_make_ico(124, 58, 237))
    sched.start()
    yield
    sched.stop()


app = FastAPI(title="OpenClaw", docs_url=None, redoc_url=None, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(chats.router)
app.include_router(upload.router)
app.include_router(push.router)
app.include_router(telegram.router)
app.include_router(admin.router)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
