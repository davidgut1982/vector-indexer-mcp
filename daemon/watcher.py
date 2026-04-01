"""File watcher daemon for automatic vector indexing.

Monitors configured directories for file changes and populates the index queue
for processing by the IndexingWorker.
"""

import asyncio
import logging
import os
import signal
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Dict, List, Set

# Add project root to sys.path so utils/ package is findable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from watchdog.events import (
    FileSystemEventHandler,
    FileSystemEvent,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
    FileMovedEvent,
)
from watchdog.observers import Observer

from utils.db_client import get_db_client

from .config import load_config, WatcherConfig


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@dataclass
class FileEvent:
    """Represents a file system event for indexing."""

    file_path: str
    event_type: str  # 'create', 'modify', 'delete', 'move'
    dest_path: str = None  # For move events
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class DebounceQueue:
    """Queue with debouncing support for rapid file changes.

    Collects events and only processes them after a debounce period
    to avoid duplicate processing during rapid file changes.
    """

    def __init__(self, debounce_ms: int = 100):
        self.debounce_ms = debounce_ms
        self.events: Dict[str, FileEvent] = {}  # file_path -> latest event
        self.lock = Lock()

    def add(self, event: FileEvent):
        """Add event to queue, replacing any existing event for same file."""
        with self.lock:
            # For move events, we need to handle both src and dest
            if event.event_type == 'move':
                # Remove old path and add new path
                self.events.pop(event.file_path, None)
                if event.dest_path:
                    self.events[event.dest_path] = event
            else:
                # For other events, replace existing event for this file
                self.events[event.file_path] = event

    def get_ready_events(self) -> List[FileEvent]:
        """Get events that have passed the debounce period."""
        current_time = time.time()
        debounce_seconds = self.debounce_ms / 1000.0
        ready_events = []

        with self.lock:
            ready_paths = []
            for file_path, event in self.events.items():
                if current_time - event.timestamp >= debounce_seconds:
                    ready_events.append(event)
                    ready_paths.append(file_path)

            # Remove processed events
            for path in ready_paths:
                self.events.pop(path, None)

        return ready_events

    def size(self) -> int:
        """Get current queue size."""
        with self.lock:
            return len(self.events)


class IndexEventHandler(FileSystemEventHandler):
    """Handles file system events and queues them for indexing."""

    def __init__(self, config: WatcherConfig, debounce_queue: DebounceQueue):
        super().__init__()
        self.config = config
        self.queue = debounce_queue
        self.stats = {
            'events_received': 0,
            'events_queued': 0,
            'events_filtered': 0,
        }

    def _should_process(self, file_path: str) -> bool:
        """Check if file should be processed for indexing."""
        # Check exclusions
        if self.config.should_exclude_path(file_path):
            return False

        # Check file size
        try:
            if os.path.isfile(file_path):
                file_size = os.path.getsize(file_path)
                if file_size > self.config.max_file_size_bytes:
                    logger.debug(f"Skipping large file: {file_path} ({file_size} bytes)")
                    return False
        except (OSError, FileNotFoundError):
            # File might have been deleted already
            return False

        # Check extensions
        if not self.config.should_include_file(file_path):
            return False

        return True

    def on_created(self, event: FileSystemEvent):
        """Handle file creation events."""
        if event.is_directory:
            return

        self.stats['events_received'] += 1
        file_path = event.src_path

        if not self._should_process(file_path):
            self.stats['events_filtered'] += 1
            return

        logger.debug(f"File created: {file_path}")
        self.queue.add(FileEvent(file_path=file_path, event_type='create'))
        self.stats['events_queued'] += 1

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events."""
        if event.is_directory:
            return

        self.stats['events_received'] += 1
        file_path = event.src_path

        if not self._should_process(file_path):
            self.stats['events_filtered'] += 1
            return

        logger.debug(f"File modified: {file_path}")
        self.queue.add(FileEvent(file_path=file_path, event_type='modify'))
        self.stats['events_queued'] += 1

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion events."""
        if event.is_directory:
            return

        self.stats['events_received'] += 1
        file_path = event.src_path

        # For deletions, we don't check file existence
        # but we still check exclude patterns
        if self.config.should_exclude_path(file_path):
            self.stats['events_filtered'] += 1
            return

        logger.debug(f"File deleted: {file_path}")
        self.queue.add(FileEvent(file_path=file_path, event_type='delete'))
        self.stats['events_queued'] += 1

    def on_moved(self, event: FileSystemEvent):
        """Handle file move/rename events."""
        if event.is_directory:
            return

        self.stats['events_received'] += 1
        src_path = event.src_path
        dest_path = event.dest_path if isinstance(event, FileMovedEvent) else None

        # Check if destination should be processed
        if dest_path and not self._should_process(dest_path):
            self.stats['events_filtered'] += 1
            return

        logger.debug(f"File moved: {src_path} -> {dest_path}")
        self.queue.add(
            FileEvent(file_path=src_path, event_type='move', dest_path=dest_path)
        )
        self.stats['events_queued'] += 1


class FileWatcherDaemon:
    """Main daemon that watches directories and manages the index queue."""

    def __init__(self, config_path: str = None):
        self.config = load_config(config_path)
        self.debounce_queue = DebounceQueue(debounce_ms=self.config.debounce_ms)
        self.observer = Observer()
        self.shutdown_event = Event()
        self.processor_thread = None
        self.db = None

        # Statistics
        self.stats = {
            'start_time': datetime.now(),
            'batches_processed': 0,
            'total_queued': 0,
        }

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown_event.set()

    def _init_database(self):
        """Initialize database client."""
        self.db = get_db_client()
        logger.info(f"Connected to database: {type(self.db).__name__}")

    def _insert_batch(self, events: List[FileEvent]):
        """Insert a batch of events into the index queue."""
        if not events:
            return

        records = []
        for event in events:
            record = {
                'file_path': event.file_path,
                'event': event.event_type,
                'priority': 1,  # Default priority
                'status': 'pending',
            }

            # Add dest_path for move events (stored in old_path column)
            if event.event_type == 'move' and event.dest_path:
                record['old_path'] = event.dest_path

            records.append(record)

        try:
            # Insert batch into queue (schema-qualified)
            result = self.db.table('vectors.index_queue').insert(records).execute()
            logger.info(f"Inserted {len(records)} events into queue")
            self.stats['batches_processed'] += 1
            self.stats['total_queued'] += len(records)
        except Exception as e:
            logger.error(f"Failed to insert batch: {e}")

    def _process_queue(self):
        """Background thread that processes the debounce queue."""
        logger.info("Queue processor thread started")

        while not self.shutdown_event.is_set():
            try:
                # Get ready events
                ready_events = self.debounce_queue.get_ready_events()

                if ready_events:
                    # Process in batches
                    for i in range(0, len(ready_events), self.config.batch_size):
                        batch = ready_events[i : i + self.config.batch_size]
                        self._insert_batch(batch)

                # Sleep briefly to avoid busy-waiting
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in queue processor: {e}")
                time.sleep(1)

        logger.info("Queue processor thread stopped")

    def _setup_watchers(self):
        """Setup file system watchers for configured paths."""
        event_handler = IndexEventHandler(self.config, self.debounce_queue)

        for watch_path in self.config.watch_paths:
            path = Path(watch_path)
            if not path.exists():
                logger.warning(f"Watch path does not exist: {watch_path}")
                continue

            logger.info(f"Watching: {watch_path}")
            self.observer.schedule(event_handler, str(path), recursive=True)

        return event_handler

    def start(self):
        """Start the file watcher daemon."""
        logger.info("Starting Vector Indexer File Watcher Daemon")
        logger.info(f"Configuration: {len(self.config.watch_paths)} watch paths")
        logger.info(f"Debounce: {self.config.debounce_ms}ms")
        logger.info(f"Batch size: {self.config.batch_size}")

        # Initialize database client
        self._init_database()

        # Setup watchers
        event_handler = self._setup_watchers()

        # Start observer
        self.observer.start()
        logger.info("File system observer started")

        # Start queue processor thread
        self.processor_thread = Thread(target=self._process_queue, daemon=True)
        self.processor_thread.start()

        # Main loop - log stats periodically
        try:
            while not self.shutdown_event.is_set():
                time.sleep(60)  # Log stats every minute

                # Log statistics
                uptime = datetime.now() - self.stats['start_time']
                logger.info(
                    f"Stats - Uptime: {uptime}, "
                    f"Queue size: {self.debounce_queue.size()}, "
                    f"Events queued: {event_handler.stats['events_queued']}, "
                    f"Events filtered: {event_handler.stats['events_filtered']}, "
                    f"Batches processed: {self.stats['batches_processed']}, "
                    f"Total queued: {self.stats['total_queued']}"
                )

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            self.shutdown_event.set()

        # Cleanup
        self.stop()

    def stop(self):
        """Stop the file watcher daemon gracefully."""
        logger.info("Stopping daemon...")

        # Stop observer
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=5)

        # Wait for processor thread
        if self.processor_thread and self.processor_thread.is_alive():
            self.processor_thread.join(timeout=5)

        # Process any remaining events
        remaining_events = self.debounce_queue.get_ready_events()
        if remaining_events:
            logger.info(f"Processing {len(remaining_events)} remaining events")
            self._insert_batch(remaining_events)

        logger.info("Daemon stopped")


def main():
    """Main entry point for the watcher daemon."""
    try:
        # Load configuration
        config_path = os.getenv("WATCHER_CONFIG")
        daemon = FileWatcherDaemon(config_path=config_path)

        # Start daemon
        daemon.start()

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
