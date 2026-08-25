"""Florence MCP server paketi.

MCP (Model Context Protocol) sunucusu: ``florence-sdk`` SDK'sinin 92 tool'luk
ince adaptoru. Tasarim: ``docs/mcp-design.md``; kurulum: ``docs/mcp-setup.md``.

Kullanim (stdio):
    florence-mcp

Programatik (in-process test / ozel transport):
    from florence_mcp import create_server
    server = create_server()
    server.run()
"""

from .server import INSTRUCTIONS, create_server, main

__version__ = "0.3.0"

__all__ = ["INSTRUCTIONS", "__version__", "create_server", "main"]
