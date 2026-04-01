"""Test script for the file watcher daemon.

Tests configuration loading, event handling, and debouncing logic.
"""

import os
import sys
import time
import tempfile
from pathlib import Path

# Import only watcher components to avoid heavy dependencies
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daemon.config import load_config, WatcherConfig
from daemon.watcher import FileEvent, DebounceQueue


def test_config_loading():
    """Test configuration loading from YAML."""
    print("\n=== Testing Configuration Loading ===")

    config = load_config()

    print(f"Watch paths: {len(config.watch_paths)}")
    for path in config.watch_paths:
        print(f"  - {path}")

    print(f"\nExclude patterns: {len(config.exclude_patterns)}")
    print(f"Include extensions: {len(config.include_extensions)}")
    print(f"Max file size: {config.max_file_size_mb} MB")
    print(f"Debounce delay: {config.debounce_ms} ms")
    print(f"Batch size: {config.batch_size}")

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
    ]

    for file_path, expected, description in test_cases:
        should_include = config.should_include_file(file_path)
        should_exclude = config.should_exclude_path(file_path)
        result = should_include and not should_exclude

        status = "✓" if result == expected else "✗"
        print(f"{status} {description}: {file_path}")
        print(f"    Include: {should_include}, Exclude: {should_exclude}, Result: {result}")

    print("\n✓ Configuration loading test passed")


def test_debounce_queue():
    """Test debounce queue functionality."""
    print("\n=== Testing Debounce Queue ===")

    queue = DebounceQueue(debounce_ms=50)

    # Add events
    print("\nAdding events...")
    queue.add(FileEvent(file_path="/test/file1.py", event_type="create"))
    queue.add(FileEvent(file_path="/test/file2.py", event_type="modify"))
    queue.add(FileEvent(file_path="/test/file1.py", event_type="modify"))  # Should replace

    print(f"Queue size: {queue.size()}")

    # Events should not be ready yet
    ready = queue.get_ready_events()
    print(f"Ready events (immediate): {len(ready)}")
    assert len(ready) == 0, "Events should not be ready immediately"

    # Wait for debounce
    print("\nWaiting for debounce period (100ms)...")
    time.sleep(0.1)

    # Now events should be ready
    ready = queue.get_ready_events()
    print(f"Ready events (after debounce): {len(ready)}")
    print("Events:")
    for event in ready:
        print(f"  - {event.file_path}: {event.event_type}")

    assert len(ready) == 2, f"Expected 2 events, got {len(ready)}"

    # Queue should be empty now
    print(f"Queue size after retrieval: {queue.size()}")
    assert queue.size() == 0, "Queue should be empty"

    print("\n✓ Debounce queue test passed")


def test_rapid_changes():
    """Test debouncing with rapid file changes."""
    print("\n=== Testing Rapid Changes ===")

    queue = DebounceQueue(debounce_ms=100)

    # Simulate rapid changes to same file
    print("\nSimulating 10 rapid changes to file1.py...")
    for i in range(10):
        queue.add(FileEvent(file_path="/test/file1.py", event_type="modify"))
        time.sleep(0.01)  # 10ms between changes

    print(f"Queue size: {queue.size()}")
    assert queue.size() == 1, "Should have only 1 event (deduplicated)"

    # Wait for debounce
    time.sleep(0.15)

    ready = queue.get_ready_events()
    print(f"Ready events: {len(ready)}")
    assert len(ready) == 1, "Should get 1 event after debounce"
    assert ready[0].event_type == "modify", "Should be the latest event type"

    print("\n✓ Rapid changes test passed")


def test_move_events():
    """Test move event handling."""
    print("\n=== Testing Move Events ===")

    queue = DebounceQueue(debounce_ms=50)

    # Add move event
    print("\nAdding move event...")
    queue.add(
        FileEvent(
            file_path="/test/old_path.py",
            event_type="move",
            dest_path="/test/new_path.py",
        )
    )

    print(f"Queue size: {queue.size()}")

    time.sleep(0.1)

    ready = queue.get_ready_events()
    print(f"Ready events: {len(ready)}")
    assert len(ready) == 1, "Should have 1 move event"

    event = ready[0]
    print(f"Event: {event.file_path} -> {event.dest_path}")
    assert event.event_type == "move", "Should be a move event"
    assert event.dest_path == "/test/new_path.py", "Should have destination path"

    print("\n✓ Move event test passed")


def test_batch_processing():
    """Test batch event retrieval."""
    print("\n=== Testing Batch Processing ===")

    queue = DebounceQueue(debounce_ms=50)

    # Add multiple events
    print("\nAdding 5 events...")
    for i in range(5):
        queue.add(FileEvent(file_path=f"/test/file{i}.py", event_type="create"))

    print(f"Queue size: {queue.size()}")

    # Wait for debounce
    time.sleep(0.1)

    # Get ready events
    ready = queue.get_ready_events()
    print(f"Retrieved {len(ready)} events")

    for event in ready:
        print(f"  - {event.file_path}")

    assert len(ready) == 5, f"Expected 5 events, got {len(ready)}"

    print("\n✓ Batch processing test passed")


def main():
    """Run all tests."""
    print("Vector Indexer Watcher - Test Suite")
    print("=" * 50)

    try:
        test_config_loading()
        test_debounce_queue()
        test_rapid_changes()
        test_move_events()
        test_batch_processing()

        print("\n" + "=" * 50)
        print("✓ All tests passed!")
        print("=" * 50)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
