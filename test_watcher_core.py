"""Core test script for file watcher components.

Tests only the essential components (config and queue logic) without
requiring the full watcher module with all its dependencies.
"""

import os
import sys
import time
import importlib.util
from dataclasses import dataclass
from collections import defaultdict
from threading import Lock

# Load config module directly
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

base_dir = os.path.dirname(os.path.abspath(__file__))
config_module = load_module("config", os.path.join(base_dir, "daemon", "config.py"))

# Import the components we need from watcher manually (copy the classes)
@dataclass
class FileEvent:
    """Represents a file system event for indexing."""
    file_path: str
    event_type: str  # 'create', 'modify', 'delete', 'move'
    dest_path: str = None
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class DebounceQueue:
    """Queue with debouncing support for rapid file changes."""

    def __init__(self, debounce_ms: int = 100):
        self.debounce_ms = debounce_ms
        self.events = {}  # file_path -> latest event
        self.lock = Lock()

    def add(self, event: FileEvent):
        """Add event to queue, replacing any existing event for same file."""
        with self.lock:
            if event.event_type == 'move':
                # Remove old path and add new path
                self.events.pop(event.file_path, None)
                if event.dest_path:
                    self.events[event.dest_path] = event
            else:
                # For other events, replace existing event for this file
                self.events[event.file_path] = event

    def get_ready_events(self):
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

    def size(self):
        """Get current queue size."""
        with self.lock:
            return len(self.events)


def test_config_loading():
    """Test configuration loading from YAML."""
    print("\n=== Testing Configuration Loading ===")

    cfg = config_module.load_config()

    print(f"Watch paths: {len(cfg.watch_paths)}")
    for path in cfg.watch_paths:
        print(f"  - {path}")

    print(f"\nConfiguration Details:")
    print(f"  Exclude patterns: {len(cfg.exclude_patterns)}")
    print(f"  Include extensions: {len(cfg.include_extensions)}")
    print(f"  Max file size: {cfg.max_file_size_mb} MB ({cfg.max_file_size_bytes:,} bytes)")
    print(f"  Debounce delay: {cfg.debounce_ms} ms")
    print(f"  Batch size: {cfg.batch_size}")

    # Test filtering
    print("\n--- Testing File Filtering ---")

    test_cases = [
        ("/srv/latvian_mcp/server.py", True, "Python file"),
        ("/srv/latvian_mcp/README.md", True, "Markdown file"),
        ("/srv/latvian_mcp/__pycache__/test.pyc", False, "Pycache file"),
        ("/srv/latvian_mcp/.git/config", False, "Git directory"),
        ("/srv/latvian_mcp/venv/lib/test.py", False, "Virtual environment"),
        ("/srv/latvian_mcp/data/notes.txt", True, "Text file"),
        ("/srv/latvian_mcp/config.json", True, "JSON file"),
        ("/srv/latvian_mcp/app.log", False, "Log file"),
        ("/srv/latvian_mcp/script.sh", True, "Shell script"),
        ("/srv/latvian_mcp/config.yaml", True, "YAML file"),
    ]

    passed = 0
    failed = 0

    for file_path, expected, description in test_cases:
        should_include = cfg.should_include_file(file_path)
        should_exclude = cfg.should_exclude_path(file_path)
        result = should_include and not should_exclude

        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status} {description}")
        if result != expected:
            print(f"    Path: {file_path}")
            print(f"    Include: {should_include}, Exclude: {should_exclude}")
            print(f"    Result: {result}, Expected: {expected}")

    print(f"\nFiltering: {passed} passed, {failed} failed")
    assert failed == 0, f"{failed} filtering tests failed"

    print("\n✓ Configuration loading test PASSED")
    return True


def test_debounce_queue():
    """Test debounce queue functionality."""
    print("\n=== Testing Debounce Queue ===")

    queue = DebounceQueue(debounce_ms=50)

    # Add events
    print("\nAdding 3 events...")
    queue.add(FileEvent(file_path="/test/file1.py", event_type="create"))
    queue.add(FileEvent(file_path="/test/file2.py", event_type="modify"))
    queue.add(FileEvent(file_path="/test/file1.py", event_type="modify"))  # Should replace

    print(f"Queue size: {queue.size()}")
    assert queue.size() == 2, f"Expected queue size 2, got {queue.size()}"

    # Events should not be ready yet
    ready = queue.get_ready_events()
    print(f"Ready events (immediate): {len(ready)}")
    assert len(ready) == 0, "Events should not be ready immediately"

    # Wait for debounce
    print("Waiting 100ms for debounce...")
    time.sleep(0.1)

    # Now events should be ready
    ready = queue.get_ready_events()
    print(f"Ready events (after debounce): {len(ready)}")
    for event in ready:
        print(f"  - {event.file_path}: {event.event_type}")

    assert len(ready) == 2, f"Expected 2 events, got {len(ready)}"

    # Queue should be empty now
    print(f"Queue size after retrieval: {queue.size()}")
    assert queue.size() == 0, "Queue should be empty"

    print("\n✓ Debounce queue test PASSED")
    return True


def test_rapid_changes():
    """Test debouncing with rapid file changes."""
    print("\n=== Testing Rapid Changes (Deduplication) ===")

    queue = DebounceQueue(debounce_ms=100)

    # Simulate rapid changes to same file
    print("\nSimulating 10 rapid changes to file1.py...")
    for i in range(10):
        queue.add(FileEvent(file_path="/test/file1.py", event_type="modify"))
        time.sleep(0.01)  # 10ms between changes

    print(f"Queue size: {queue.size()}")
    assert queue.size() == 1, f"Expected 1 event (deduplicated), got {queue.size()}"

    # Wait for debounce
    time.sleep(0.15)

    ready = queue.get_ready_events()
    print(f"Ready events: {len(ready)}")
    assert len(ready) == 1, f"Expected 1 event, got {len(ready)}"
    assert ready[0].event_type == "modify", "Should be modify event"

    print("\n✓ Rapid changes deduplication test PASSED")
    return True


def test_move_events():
    """Test move event handling."""
    print("\n=== Testing Move Events ===")

    queue = DebounceQueue(debounce_ms=50)

    # Add move event
    print("\nAdding move event (rename)...")
    queue.add(
        FileEvent(
            file_path="/test/old_path.py",
            event_type="move",
            dest_path="/test/new_path.py",
        )
    )

    print(f"Queue size: {queue.size()}")
    assert queue.size() == 1, f"Expected 1 event, got {queue.size()}"

    time.sleep(0.1)

    ready = queue.get_ready_events()
    print(f"Ready events: {len(ready)}")
    assert len(ready) == 1, f"Expected 1 event, got {len(ready)}"

    event = ready[0]
    print(f"Move: {event.file_path} -> {event.dest_path}")
    assert event.event_type == "move", "Should be move event"
    assert event.dest_path == "/test/new_path.py", "Should have destination path"

    print("\n✓ Move event handling test PASSED")
    return True


def test_batch_processing():
    """Test batch event retrieval."""
    print("\n=== Testing Batch Processing ===")

    queue = DebounceQueue(debounce_ms=50)

    # Add multiple different files
    print("\nAdding 5 file events...")
    for i in range(5):
        queue.add(FileEvent(file_path=f"/test/file{i}.py", event_type="create"))

    print(f"Queue size: {queue.size()}")
    assert queue.size() == 5, f"Expected 5 events, got {queue.size()}"

    # Wait for debounce
    time.sleep(0.1)

    # Get ready events
    ready = queue.get_ready_events()
    print(f"Retrieved {len(ready)} events:")
    for event in ready:
        print(f"  - {event.file_path}")

    assert len(ready) == 5, f"Expected 5 events, got {len(ready)}"

    print("\n✓ Batch processing test PASSED")
    return True


def test_env_var_expansion():
    """Test environment variable expansion in config."""
    print("\n=== Testing Environment Variable Expansion ===")

    # Test ${VAR} syntax
    os.environ['TEST_VAR'] = '/test/path'
    result = config_module.expand_env_vars('${TEST_VAR}/file.txt')
    print(f"${{TEST_VAR}}/file.txt -> {result}")
    assert result == '/test/path/file.txt', f"Expected '/test/path/file.txt', got '{result}'"

    # Test $VAR syntax
    result = config_module.expand_env_vars('$TEST_VAR/file.txt')
    print(f"$TEST_VAR/file.txt -> {result}")
    assert result == '/test/path/file.txt', f"Expected '/test/path/file.txt', got '{result}'"

    # Test with non-existent var (should keep original)
    result = config_module.expand_env_vars('${NONEXISTENT}/file.txt')
    print(f"${{NONEXISTENT}}/file.txt -> {result} (unchanged)")

    print("\n✓ Environment variable expansion test PASSED")
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Vector Indexer Watcher - Core Component Test Suite")
    print("=" * 60)

    tests = [
        ("Configuration Loading", test_config_loading),
        ("Debounce Queue", test_debounce_queue),
        ("Rapid Changes (Deduplication)", test_rapid_changes),
        ("Move Events", test_move_events),
        ("Batch Processing", test_batch_processing),
        ("Environment Variable Expansion", test_env_var_expansion),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"\n✗ {test_name} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n✗ {test_name} ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    if failed == 0:
        print(f"✓ ALL {passed} TESTS PASSED!")
        print("=" * 60)
        return 0
    else:
        print(f"✗ {failed} TEST(S) FAILED ({passed} passed)")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
