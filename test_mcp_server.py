#!/usr/bin/env python3
"""
Test MCP server functionality
"""

import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import server
from src.server import app, list_tools, call_tool


async def test_list_tools():
    """Test that tools are listed correctly."""
    print("Testing list_tools()...")
    tools = await list_tools()
    print(f"✓ Found {len(tools)} tools:")
    for tool in tools:
        print(f"  - {tool.name}: {tool.description[:60]}...")
    assert len(tools) == 7, f"Expected 7 tools, got {len(tools)}"
    print()


async def test_index_status():
    """Test index_status tool."""
    print("Testing index_status tool...")
    try:
        result = await call_tool("index_status", {})
        print(f"✓ index_status returned {len(result)} TextContent item(s)")
        print(f"  Response preview: {result[0].text[:200]}...")
    except Exception as e:
        print(f"✗ index_status failed: {e}")
        raise
    print()


async def test_invalid_tool():
    """Test error handling for unknown tool."""
    print("Testing invalid tool handling...")
    result = await call_tool("nonexistent_tool", {})
    print(f"✓ Error handling works: {result[0].text[:100]}...")
    assert '"ok": false' in result[0].text or '"ok":false' in result[0].text
    print()


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Vector Indexer MCP Server - Test Suite")
    print("=" * 60)
    print()

    try:
        await test_list_tools()
        await test_index_status()
        await test_invalid_tool()

        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0

    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
