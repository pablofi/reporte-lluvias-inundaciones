import argparse
import asyncio
import json
import logging

from app.config import get_settings
from app.db import SessionLocal, engine, initialize_database
from app.services.monitor import Monitor, MonitorBusy


def main():
    parser = argparse.ArgumentParser(description="Administración de fuentes oficiales")
    parser.add_argument("command", choices=["check-sources"])
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    initialize_database()
    monitor = Monitor(SessionLocal, get_settings())
    monitor.initialize()
    try:
        results = asyncio.run(monitor.check())
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if all(item["success"] for item in results) else 1
    except MonitorBusy:
        print("Ya hay una comprobación en curso")
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
