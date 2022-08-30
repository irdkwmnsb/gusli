import pathlib

import uvicorn as uvicorn
from fastapi import FastAPI, APIRouter, UploadFile, status
from guslibot.player import *
from guslibot.web.utils import save_to_disk
import uuid
from content_size_limit_asgi import ContentSizeLimitMiddleware

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


player_r = APIRouter()


@player_r.get("/queue")
async def get_queue():
    return pl_get_player_string()


@player_r.put("/add")
async def add(file: UploadFile, displayname: str, title: str):
    path = pathlib.Path(MUSIC_FOLDER, str(uuid.uuid4()))
    save_to_disk(file.file, path)
    rq = AudioRequest(
        by_displayname=displayname,
        mrl=str(path),
        title=title,
        filename=file.filename
    )
    await pl_add(rq)
    return status.HTTP_200_OK


app.include_router(player_r, prefix="/player")

app.add_middleware(ContentSizeLimitMiddleware, max_content_size=20 * 1024 * 1024)


async def start_server():
    config = uvicorn.Config("guslibot.web.app:app", port=5000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
