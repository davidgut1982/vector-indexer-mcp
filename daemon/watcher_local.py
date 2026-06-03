"""Asyncpg-based file watcher daemon for local PostgreSQL vector indexer."""

import asyncio
import logging
import time
from pathlib import Path

import asyncpg
import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

CONFIG_PATH = "/home/david/vector-indexer-mcp/config.yaml"


class IndexEventHandler(FileSystemEventHandler):
    def __init__(self, queue, extensions, exclude_patterns):
        self.queue = queue
        self.extensions = extensions
        self.exclude_patterns = exclude_patterns
        self._debounce = {}

    def _should_index(self, path: str) -> bool:
        p = Path(path)
        if any(ex in path for ex in self.exclude_patterns):
            return False
        return p.suffix in self.extensions

    def _enqueue(self, path: str, event_type: str):
        if not self._should_index(path):
            return
        now = time.time()
        key = (path, event_type)
        self._debounce[key] = now
        try:
            self.queue.put_nowait((path, event_type, now))
        except asyncio.QueueFull:
            pass

    def on_created(self, event):
        if not event.is_directory:
            self._enqueue(event.src_path, "create")

    def on_modified(self, event):
        if not event.is_directory:
            self._enqueue(event.src_path, "modify")

    def on_deleted(self, event):
        if not event.is_directory:
            self._enqueue(event.src_path, "delete")

    def on_moved(self, event):
        if not event.is_directory:
            self._enqueue(event.src_path, "delete")
            self._enqueue(event.dest_path, "create")


class FileWatcherDaemon:
    def __init__(self, config_path: str = CONFIG_PATH):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        db = self.config["database"]
        self.dsn = f"postgresql://{db['user']}:{db['password']}@{db['host']}:{db['port']}/{db['name']}"
        w = self.config.get("watcher", {})
        self.paths = w.get("paths", [])
        self.extensions = set(w.get("extensions", [".py", ".md"]))
        self.exclude_patterns = w.get(
            "exclude_patterns", ["__pycache__", ".git", "node_modules"]
        )
        self.debounce_ms = w.get("debounce_ms", 500)
        self.queue = asyncio.Queue(maxsize=10000)

    async def start(self):
        self.pool = await asyncpg.create_pool(self.dsn)
        observer = Observer()
        handler = IndexEventHandler(self.queue, self.extensions, self.exclude_patterns)
        for path in self.paths:
            p = Path(path)
            if p.exists():
                observer.schedule(handler, str(p), recursive=True)
                logger.info(f"Watching: {path}")
            else:
                logger.warning(f"Watch path does not exist: {path}")
        observer.start()
        logger.info("FileWatcherDaemon started")
        await self._flush_loop()

    async def _flush_loop(self):
        debounce_s = self.debounce_ms / 1000
        pending = {}
        while True:
            try:
                path, event_type, ts = await asyncio.wait_for(
                    self.queue.get(), timeout=debounce_s
                )
                pending[(path, event_type)] = ts
            except asyncio.TimeoutError:
                pass
            now = time.time()
            to_flush = [
                (p, e) for (p, e), ts in list(pending.items()) if now - ts >= debounce_s
            ]
            if to_flush:
                async with self.pool.acquire() as conn:
                    for path, event_type in to_flush:
                        await conn.execute(
                            "INSERT INTO index_queue(file_path, event_type, status) VALUES($1,$2,'pending') "
                            "ON CONFLICT DO NOTHING",
                            path,
                            event_type,
                        )
                        del pending[(path, event_type)]


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    config = sys.argv[1] if len(sys.argv) > 1 else CONFIG_PATH
    daemon = FileWatcherDaemon(config)
    asyncio.run(daemon.start())
