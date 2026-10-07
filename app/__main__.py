import logging

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port)
