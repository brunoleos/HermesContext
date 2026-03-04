"""Check tool schemas in MCP server"""
import json
import sys
sys.path.insert(0, "/app")

from src.server import mcp

print("=== MCP Tool Schemas ===\n")

for name, tool in mcp._tool_manager._tools.items():
    print(f"Tool: {name}")
    print(f"Description: {tool.description}")
    print(f"Input Schema: {json.dumps(tool.input_schema, indent=2)}")
    print("---\n")
