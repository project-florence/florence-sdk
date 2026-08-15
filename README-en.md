[Türkçe versiyon](./README.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/project-florence/web/main/src/assets/florence_logo.svg" width="80" height="80" alt="Florence">
</p>

<h1 align="center">Florence SDK</h1>

<p align="center">
  <strong>Official SDK for the Florence API</strong> — terminal usage, code integration, and an MCP server for AI agents.
</p>

---

Florence is a smart investment assistant that lets you track stocks, currency rates, precious metals, and macroeconomic indicators in a single dashboard. The Florence SDK is the official toolkit for using the platform from your terminal and from your own code. Query prices, generate reports, and manage portfolios from the CLI, or connect your AI assistants to Florence through the MCP server.

## Screenshots

<p align="center">
  <img src="docs/screenshots/cli-demo.png" width="600" alt="CLI example — command output">
</p>

CLI example — price query output in the terminal

## Features

- **API Client** — Sync and async clients for using the Florence API directly from code: price queries, report generation, and portfolio operations
- **Command-Line Interface** — 94 commands for Florence from the terminal: live prices, reports, and portfolio management with `fl price THYAO`; `--json` output on every command
- **MCP Server** — Secure access to Florence for AI agents such as Claude and Cursor; 92 ready-to-use tools
- **Bot Accounts** — Create and manage bot accounts for automated operations
- **Secure Session Management** — Session tokens are stored encrypted

## Quick Start

Installation: single command for Linux/macOS — `curl -fsSL https://raw.githubusercontent.com/project-florence/florence-sdk/main/install.sh | bash`. PyPI release coming soon.

```bash
fl price THYAO --json
```

Connect the MCP server to your AI agents such as Claude and Cursor to use Florence directly from your assistant.

## Repositories

- [web](https://github.com/project-florence/web) — Web application
- [desktop](https://github.com/project-florence/desktop) — Desktop application
- [mobile](https://github.com/project-florence/mobile) — Mobile application
- [backend](https://github.com/project-florence/backend) — API server
- [api-spec](https://github.com/project-florence/api-spec) — API specification and references

## License

[AGPL-3.0](./LICENSE)
