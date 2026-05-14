"""
Backwards-compatibility shim.

Early installs configured ~/.mcp.json to invoke `-m src.server_local`.
The correct module is `src.server`, but this shim ensures both work.

See: https://github.com/davidgut1982/vector-indexer-mcp/issues/1
"""
from src.server import main  # noqa: F401

if __name__ == "__main__":
    main()
