"""Servidor local con demora configurable, para medir sin depender de httpbin.org."""
import asyncio

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="Mock con delay")


@app.get("/delay/{segundos}")
async def delay(segundos: float):
    await asyncio.sleep(min(max(segundos, 0), 30))
    return {"demora_s": segundos}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
