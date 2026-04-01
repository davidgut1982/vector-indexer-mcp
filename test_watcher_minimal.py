"""Minimal test script for the file watcher daemon.

Tests configuration loading, event handling, and debouncing logic
without any heavy dependencies.
"""

import os
import sys
import time
import importlib.util

# Load modules directly without going through __init__.py
def load_module(name, path, inject_globals=None):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # Inject globals if provided
    if inject_globals:
        for key, value in inject_globals.items():
            setattr(module, key, value)
    spec.loader.exec_module(module)
    return module

# Get base directory
base_dir = os.path.dirname(os.path.abspath(__file__))

# Load config module first
config_module = load_module("config", os.path.join(base_dir, "daemon", "config.py"))

# Load watcher module with config injected to resolve relative imports
sys.modules['daemon.config'] = config_module
watcher_module = load_module("watcher", os.path.join(base_dir, "daemon", "watcher.py"))


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
            print(f"    Include: {should_include}, Exclude: {should_exclude}, Result: {result}, Expected: {expected}")

    print(f"\nFiltering tests: {passed} passed, {failed} failed")
    assert failed == 0, f"{failed} filtering tests failed"

    print("\n✓ Configuration loading test passed")


def test_debounce_queue():
    """Test debounce queue functionality."""
    print("\n=== Testing Debounce Queue ===")

    queue = watcher_module.DebounceQueue(debounce_ms=50)

    # Add events
    print("\nAdding events...")
    queue.add(watcher_module.FileEvent(file_path="/test/file1.py", event_type="create"))
    queue.add(watcher_module.FileEvent(file_path="/test/file2.py", event_type="modify"))
    queue.add(watcher_module.FileEvent(file_path="/test/file1.py", event_type="modify"))  # Should replace

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

    queue = watcher_module.DebounceQueue(debounce_ms=100)

    # Simulate rapid changes to same file
    print("\nSimulating 10 rapid changes to file1.py...")
    for i in range(10):
        queue.add(watcher_module.FileEvent(file_path="/test/file1.py", event_type="modify"))
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

    queue = watcher_module.DebounceQueue(debounce_ms=50)

    # Add move event
    print("\nAdding move event...")
    queue.add(
        watcher_module.FileEvent(
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

    queue = watcher_module.DebounceQueue(debounce_ms=50)

    # Add multiple events
    print("\nAdding 5 events...")
    for i in range(5):
        queue.add(watcher_module.FileEvent(file_path=f"/test/file{i}.py", event_type="create"))

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
    print(f"${{NONEXISTENT}}/file.txt -> {result}")
    assert result == '${NONEXISTENT}/file.txt', f"Expected '${{NONEXISTENT}}/file.txt', got '{result}'"

    print("\n✓ Environment variable expansion test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Vector Indexer Watcher - Test Suite")
    print("=" * 60)

    try:
        test_config_loading()
        test_debounce_queue()
        test_rapid_changes()
        test_move_events()
        test_batch_processing()
        test_env_var_expansion()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED!")
        print("=" * 60)

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
