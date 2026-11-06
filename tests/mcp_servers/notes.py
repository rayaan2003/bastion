"""A real MCP server, built with the official SDK, for the end-to-end test."""

from mcp.server.mcpserver import MCPServer

server = MCPServer("notes")
notes = {"todo": "buy milk"}


@server.tool()
def read_note(name: str) -> str:
    """Read a note."""
    return notes[name]


@server.tool()
def delete_note(name: str) -> str:
    """Delete a note."""
    del notes[name]
    return f"deleted {name}"


server.run()
