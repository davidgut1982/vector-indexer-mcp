# ContextForge Gateway Tool Exposure Analysis

**Research Date:** 2025-12-18
**Researcher:** Research Agent
**Purpose:** Understand ContextForge gateway tool aggregation mechanism and troubleshoot why tools are registered but not visible to Claude Code

---

## Executive Summary

ContextForge is an MCP gateway that aggregates tools from multiple backend MCP servers and exposes them through a unified endpoint. After researching documentation, architecture, and known issues, I've identified **the likely root cause** of tools being registered but not visible to Claude Code:

**Key Finding:** Tools registered in the gateway must be **explicitly associated with a virtual server** via the `associatedTools` configuration for them to be exposed to clients. Simply registering backend MCP servers is insufficient.

---

## How ContextForge Aggregates Tools

### 1. Tool Discovery Process

ContextForge acts as a **federated registry** that:

1. **Backend Registration:** Accepts MCP servers via POST to `/gateways` endpoint
2. **Tool Catalog:** Maintains unified catalog of all tools accessible via `GET /tools`
3. **Virtual Server Creation:** Bundles specific tools into client-facing endpoints
4. **Client Exposure:** Exposes tools through multiple transports (stdio, SSE, WebSocket, HTTP)

```
┌─────────────────┐
│ Backend MCP #1  │──┐
│ (tools A, B, C) │  │
└─────────────────┘  │
                     ├──► Gateway Tool Catalog
┌─────────────────┐  │     (all tools indexed)
│ Backend MCP #2  │──┤              │
│ (tools D, E, F) │  │              ├──► Virtual Server #1
└─────────────────┘  │              │     (tools A, D)
                     │              │
┌─────────────────┐  │              ├──► Virtual Server #2
│ REST API #3     │──┘              │     (tools B, C, E, F)
│ (tools G, H)    │                 │
└─────────────────┘                 ▼
                              Client (Claude Code)
                              connects to virtual server
```

### 2. Tool Naming and Namespacing

**Limited Documentation:** The ContextForge documentation does NOT provide explicit details about:
- Tool prefix/namespace patterns when aggregating multiple servers
- `GATEWAY_TOOL_NAME_SEPARATOR` setting (mentioned in some sources but not documented)
- How tools with identical names from different backends are disambiguated

**What IS Documented:**
- Tools maintain UUID-based identity management
- "Namespace Composite Keys & UUIDs for robust tool identity across federated servers"
- Each tool receives a unique ID in the catalog (e.g., `"6018ca46d32a4ac6b4c054c13a1726a2"`)

**Inference:** Tools likely retain original names but are tracked internally by UUIDs. No evidence of automatic prefixing like `mcp__servername__toolname`.

---

## How Tools Are Exposed to Clients

### Configuration Requirement: Virtual Servers

**CRITICAL FINDING:** Tools do NOT automatically appear to clients after backend registration.

**Required Steps:**

1. **Register Backend MCP Server:**
   ```bash
   curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"url":"http://backend-server:8000"}' \
     http://localhost:4444/gateways
   ```

2. **Get Tool IDs from Catalog:**
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:4444/tools | jq
   ```

3. **Create Virtual Server with associatedTools:**
   ```bash
   curl -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "my_virtual_server",
       "description": "Collection of tools for Claude",
       "associatedTools": [
         "6018ca46d32a4ac6b4c054c13a1726a2",
         "abc123def456..."
       ]
     }' \
     http://localhost:4444/servers | jq
   ```

4. **Configure Claude Code to Connect to Virtual Server:**
   ```json
   {
     "mcpServers": {
       "contextforge-gateway": {
         "command": "python",
         "args": ["-m", "mcpgateway.wrapper"],
         "env": {
           "MCP_AUTH": "Bearer your-token-here",
           "MCP_SERVER_URL": "http://localhost:4444/servers/UUID_OF_VIRTUAL_SERVER",
           "MCP_TOOL_CALL_TIMEOUT": "120"
         }
       }
     }
   }
   ```

### Transport Mechanisms

ContextForge supports multiple transports for exposing tools:

| Transport | Use Case | Configuration |
|-----------|----------|---------------|
| **stdio** | Claude Desktop/Code | `mcpgateway.wrapper` module |
| **SSE** | Web clients, long-polling | Direct HTTP connection |
| **WebSocket** | Real-time bidirectional | WebSocket endpoint |
| **Streamable HTTP** | HTTP streaming | HTTP streaming API |

For Claude Code, **stdio via wrapper** is the standard approach.

---

## Known Issues with Tool Visibility

### Issue #1: Tools Registered but Not Appearing

**Symptoms:**
- Backend MCP servers show "Connected" in gateway
- `GET /tools` returns the tools in catalog
- Claude Code doesn't see the tools
- No errors in logs

**Root Cause:** Tools are in the catalog but NOT associated with a virtual server that Claude Code is connected to.

**Solution:** Create virtual server with `associatedTools` array containing tool UUIDs.

### Issue #2: Claude Desktop/Code MCP Tool Registration Failures

From GitHub issues research:

- **Issue #467:** "Cannot get any MCP tool calls working at all in Claude Code, despite them working in Claude Desktop"
- **Issue #5241:** "MCP Tools Not Registering Despite Successful Server Connection"
- **Issue #3426:** "Claude Code fails to expose MCP tools to AI sessions when running a local MCP server"

**Common Patterns:**
- Tools work in Claude Desktop but not Claude Code
- Server shows "Connected" but tools don't appear
- Tool registration step fails silently

**Workarounds:**
1. Completely quit and restart Claude Desktop/Code after configuration changes
2. Enable Developer Mode to access MCP logs
3. Verify stdio wrapper configuration includes proper bearer token
4. Check virtual server UUID is correct in `MCP_SERVER_URL`

### Issue #3: Docker MCP Gateway Specific

**Problem:** Docker MCP Gateway tools work in VSCode Copilot but fail in Claude Desktop/Code

**Potential Causes:**
- Transport protocol mismatch
- Authentication header issues
- stdio wrapper configuration errors

---

## Configuration for Claude Code Integration

### Step-by-Step Setup

**1. Start ContextForge Gateway:**
```bash
docker run -d \
  -p 4444:4444 \
  -e MCPGATEWAY_BEARER_TOKEN=your-secret-token \
  -e MCPGATEWAY_UI_ENABLED=true \
  ghcr.io/ibm/mcp-context-forge:latest
```

**2. Register Backend MCP Servers:**
```bash
# Register vector-indexer-mcp
curl -X POST -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url":"http://localhost:8000"}' \
  http://localhost:4444/gateways

# Verify registration
curl -H "Authorization: Bearer your-secret-token" \
  http://localhost:4444/gateways | jq
```

**3. Get Tool UUIDs:**
```bash
curl -H "Authorization: Bearer your-secret-token" \
  http://localhost:4444/tools | jq '.[] | {name: .name, id: .id}'
```

**4. Create Virtual Server:**
```bash
# Example: Create virtual server with vector search tools
curl -X POST -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "vector-search-server",
    "description": "Vector indexing and search tools",
    "associatedTools": [
      "uuid-of-search_semantic",
      "uuid-of-search_lexical",
      "uuid-of-search_hybrid",
      "uuid-of-index_status",
      "uuid-of-reindex_path"
    ]
  }' \
  http://localhost:4444/servers | jq
```

**5. Get Virtual Server UUID:**
```bash
curl -H "Authorization: Bearer your-secret-token" \
  http://localhost:4444/servers | jq
```

**6. Configure Claude Code:**
Edit `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "contextforge-gateway": {
      "command": "python",
      "args": ["-m", "mcpgateway.wrapper"],
      "env": {
        "MCP_AUTH": "Bearer your-secret-token",
        "MCP_SERVER_URL": "http://localhost:4444/servers/<VIRTUAL_SERVER_UUID>",
        "MCP_TOOL_CALL_TIMEOUT": "120",
        "MCP_WRAPPER_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

**7. Restart Claude Code:**
Completely quit and restart Claude Code for configuration to take effect.

---

## Troubleshooting Tool Visibility

### Diagnostic Checklist

**1. Verify Backend Registration:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:4444/gateways | jq
```
Expected: Backend server listed with status "active"

**2. Check Tool Catalog:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:4444/tools | jq
```
Expected: All tools from backend servers listed

**3. Verify Virtual Server Exists:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:4444/servers | jq
```
Expected: Virtual server with correct `associatedTools` array

**4. Test Virtual Server Directly:**
```bash
npx -y @modelcontextprotocol/inspector
# Transport: SSE
# URL: http://localhost:4444/servers/<UUID>
# Headers: Authorization: Bearer <TOKEN>
```
Expected: Tools appear in MCP Inspector

**5. Check stdio Wrapper:**
```bash
# Test wrapper directly
python -m mcpgateway.wrapper
```
Expected: No import errors, connects successfully

**6. Review Claude Code Logs:**
Enable Developer Mode in Claude Code and check MCP logs for:
- Connection failures
- Authentication errors
- Tool registration failures

### Common Fixes

| Problem | Solution |
|---------|----------|
| Tools in catalog but not visible | Create virtual server with `associatedTools` |
| Authentication errors | Verify `MCP_AUTH` bearer token matches gateway token |
| Connection timeout | Increase `MCP_TOOL_CALL_TIMEOUT` to 180+ |
| stdio wrapper fails | Install gateway: `pip install mcp-contextforge-gateway` |
| Changes not reflected | Completely quit and restart Claude Code |
| Wrong virtual server | Verify UUID in `MCP_SERVER_URL` matches `/servers` output |

---

## Answer to Key Research Questions

### 1. How does ContextForge aggregate tools from multiple backend MCP servers?

ContextForge maintains a **unified tool catalog** that indexes all tools from registered backend servers. Each tool receives a UUID for internal tracking. Backend servers are registered via `/gateways` API, and their tools are automatically discovered and added to the catalog.

### 2. How are tools exposed/registered to clients like Claude Code?

Tools are exposed through **virtual servers** that bundle specific tools via `associatedTools` configuration. Clients connect to virtual server endpoints (not the gateway root) to access curated tool collections. The `mcpgateway.wrapper` module bridges stdio clients like Claude Code to the gateway.

### 3. Is there a tool prefix/namespace system? How does it work?

**Documentation is unclear** on this. The gateway uses "namespace composite keys & UUIDs" internally but doesn't explicitly document tool prefixing patterns. No evidence of automatic prefixes like `mcp__servername__toolname`. Tools appear to retain original names with UUID-based disambiguation.

### 4. What configuration is needed for tools to appear in client's available functions?

**Required Configuration:**
1. Backend MCP server registered in gateway (`POST /gateways`)
2. Virtual server created with `associatedTools` array (`POST /servers`)
3. Claude Code configured with stdio wrapper pointing to virtual server UUID
4. Bearer token authentication configured in both gateway and client

### 5. Is there a tool discovery endpoint or mechanism?

Yes, multiple discovery mechanisms:
- `GET /tools` - Complete tool catalog
- `GET /servers` - List virtual servers
- `GET /gateways` - List registered backends
- MCP Inspector CLI for interactive exploration
- Admin UI (if `MCPGATEWAY_UI_ENABLED=true`)

### 6. Are there known issues with tools not appearing after server registration?

**Yes, common issues:**
- Tools registered but not associated with virtual server
- Claude Code doesn't detect configuration changes without full restart
- stdio wrapper authentication failures
- Tool registration failures in Claude Code (GitHub issues #467, #5241, #3426)
- Transport protocol mismatches between gateway and client

---

## Recommended Solution for vector-indexer-mcp

Based on this research, to expose vector-indexer-mcp tools through ContextForge to Claude Code:

**Step 1: Register vector-indexer-mcp as backend**
```bash
curl -X POST -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"http://localhost:8000"}' \
  http://localhost:4444/gateways
```

**Step 2: Get tool UUIDs**
```bash
curl -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN" \
  http://localhost:4444/tools | jq '.[] | select(.name | contains("search") or contains("index")) | {name, id}'
```

**Step 3: Create virtual server with ALL vector search tools**
```bash
curl -X POST -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "vector-indexer",
    "description": "Semantic code search and indexing tools",
    "associatedTools": [
      "<uuid-of-search_semantic>",
      "<uuid-of-search_lexical>",
      "<uuid-of-search_hybrid>",
      "<uuid-of-search_similar_files>",
      "<uuid-of-index_status>",
      "<uuid-of-reindex_path>",
      "<uuid-of-get_file_chunks>"
    ]
  }' \
  http://localhost:4444/servers | jq -r '.id'
```

**Step 4: Configure Claude Code with virtual server UUID**
Edit `~/.claude/settings.json`:
```json
{
  "mcpServers": {
    "vector-indexer-gateway": {
      "command": "python",
      "args": ["-m", "mcpgateway.wrapper"],
      "env": {
        "MCP_AUTH": "Bearer $MCPGATEWAY_BEARER_TOKEN",
        "MCP_SERVER_URL": "http://localhost:4444/servers/<VIRTUAL_SERVER_UUID>",
        "MCP_TOOL_CALL_TIMEOUT": "180"
      }
    }
  }
}
```

**Step 5: Verify and restart**
```bash
# Test with MCP Inspector
npx -y @modelcontextprotocol/inspector

# Completely quit and restart Claude Code
```

---

## Sources

- [GitHub - IBM/mcp-context-forge](https://github.com/IBM/mcp-context-forge)
- [MCP Context Forge Documentation](https://ibm.github.io/mcp-context-forge/)
- [ContextForge Gateway Workshop](https://contextforge-org.github.io/mcp-workshop/mcp-gateway/)
- [ContextForge MCP Gateway: The Missing Proxy & Registry for AI Tools](https://medium.com/@crivetimihai/mcp-gateway-the-missing-proxy-for-ai-tools-2b16d3b018d5)
- [MCP Context Forge Gateway - Try it now!](https://dev.to/aairom/mcp-context-forge-gateway-try-it-now-136f)
- [Comparing MCP Gateways - Moesif Blog](https://www.moesif.com/blog/monitoring/model-context-protocol/Comparing-MCP-Model-Context-Protocol-Gateways/)
- [Claude Code Issue #467 - MCP tools not working](https://github.com/anthropics/claude-code/issues/467)
- [Claude Code Issue #5241 - MCP Tools Not Registering](https://github.com/anthropics/claude-code/issues/5241)
- [Claude Code Issue #3426 - Fails to expose MCP tools](https://github.com/anthropics/claude-code/issues/3426)
- [Model Context Protocol - Connect to local servers](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
- [MCP Services Not Working - Silver Bullet Approach](https://medium.com/@kaue.tech/mcp-services-not-working-a-silver-bullet-approach-claude-mcp-agent-tutorial-4117c28613b1)

---

## Next Steps

1. **Verify backend registration** - Check if vector-indexer-mcp appears in `/gateways`
2. **Get actual tool UUIDs** - Query `/tools` endpoint for vector-indexer tool IDs
3. **Create virtual server** - Bundle all 7 vector-indexer tools
4. **Update Claude Code config** - Point to virtual server UUID, not gateway root
5. **Test with MCP Inspector** - Verify tools appear before testing in Claude Code
6. **Full restart** - Quit and restart Claude Code to load new configuration

**Expected Outcome:** All 7 vector-indexer-mcp tools appear in Claude Code's available functions with proper tool schemas and descriptions.
