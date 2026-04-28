
<img width="1024" height="559" alt="image" src="https://github.com/user-attachments/assets/cc20e7e0-8ac2-4424-9ced-4809b6f83f71" />

-------

*Written with GLM-5.1 with Opencode*

A standalone Python CLI tool and MCP server that parses KiCad v6/v7/v8 project directories, extracts hierarchical schematic data (components, properties, instances, and nets), and outputs a token-optimized YAML representation for use as LLM context when converting KiCad circuits to [Atopile](https://atopile.io/) (`.ato`) projects.

## Features

- Parses hierarchical KiCad schematics via `kiutils`
- Extracts components with designator, value, footprint, and LCSC part numbers
- Generates accurate netlists using the official `kicad-cli` tool
- Filters out noise (unconnected nets, power flags, invalid LCSC numbers)
- Outputs token-efficient YAML (compact component format, no empty fields)
- Dual interface: CLI tool + MCP server for LLM integration

## Requirements

- Python 3.10+
- KiCad 7.0+ (for `kicad-cli` netlist generation)
- See `requirements.txt` for Python dependencies

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## CLI Usage

```bash
python main.py <project_path> [options]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `project_path` | Path to KiCad project directory, `.kicad_sch`, or `.kicad_pro` file |

**Options:**

| Flag | Description |
|------|-------------|
| `-o, --output` | Output file path (default: `./kicad-atopile-conversion-context.md`) |
| `-v, --verbose` | Enable debug logging |
| `-q, --quiet` | Suppress all output except fatal errors |

**Example:**

```bash
python main.py ~/projects/my-board/ -o context.yaml -v
```

## MCP Server

The server exposes a `parse_kicad_project` tool over stdio for LLM integration:

```bash
python server.py
```

**Tool signature:**

- `parse_kicad_project(project_path: str) -> str` — Returns raw YAML of the parsed circuit

Add to your MCP client config:

```json
{
  "mcpServers": {
    "kicad-atopile": {
      "command": "/path/to/.venv/bin/python",
      "args": ["/path/to/server.py"]
    }
  }
}
```

## Output Format

Components are stored as a compact dict mapping designator to a property array:

```yaml
components:
  R1: ["10k", "Resistor_SMD:R_0402_1005Metric", "C25904"]
  C1: ["100nF", "Capacitor_SMD:C_0402_1005Metric"]
```

Array elements: `[value, footprint]` or `[value, footprint, lcsc_part]` when an LCSC number exists.

Nets are filtered to remove `unconnected-*` entries and mapped per sheet with hierarchical pin references:

```yaml
nets:
  GND: ["R1.2", "motor_driver.GND"]
  VDD: ["R1.1"]
```

## Agent Instructions: Installing This MCP Server

Follow these steps to install this MCP server on the user's machine so it can be used with an LLM client.

### Prerequisites Check

1. Verify Python 3.10+ is installed:
   ```bash
   python3 --version
   ```
   If not found, install it first (e.g. `brew install python` on macOS, `sudo apt install python3 python3-venv` on Linux).

2. Verify KiCad 7.0+ is installed and `kicad-cli` is on PATH:
   ```bash
   kicad-cli --version
   ```
   If not found, common locations to check:
   - macOS: `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`
   - Linux: `/usr/bin/kicad-cli` or `/usr/local/bin/kicad-cli`
   If KiCad is not installed, the server will still run but netlist extraction will fail with a clear error message when invoked.

### Installation Steps

1. Clone the repository to a permanent location:
   ```bash
   git clone <repo-url> <install-dir>
   ```
   Replace `<install-dir>` with a stable path (e.g. `~/tools/ki-catopile-contgen`).

2. Create a virtual environment and install dependencies:
   ```bash
   cd <install-dir>
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

3. Verify the installation by running tests:
   ```bash
   .venv/bin/python -m unittest tests.test_pipeline -v
   ```
   All tests should pass.

4. Record the absolute paths you'll need for the config:
   ```bash
   echo "Python: $(realpath .venv/bin/python)"
   echo "Server: $(realpath server.py)"
   ```

### Registering with an MCP Client

Add the server to the client's MCP configuration. The exact config file location depends on the client:

| Client | Config Path |
|--------|-------------|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Linux) | `~/.config/Claude/claude_desktop_config.json` |
| VS Code (Copilot) | `.vscode/mcp.json` in workspace or `~/.vscode/mcp.json` globally |
| Cursor | `~/.cursor/mcp.json` |

Add this entry to the `mcpServers` object in the config file:

```json
{
  "mcpServers": {
    "kicad-atopile": {
      "command": "<install-dir>/.venv/bin/python",
      "args": ["<install-dir>/server.py"]
    }
  }
}
```

Replace `<install-dir>` with the actual absolute path from step 4.

### Verification

1. Restart the MCP client after updating the config.
2. The tool `parse_kicad_project` should appear in the client's available tools.
3. Test with any KiCad project:
   - Call `parse_kicad_project` with `project_path` set to a `.kicad_sch` file or project directory.
   - The tool should return a YAML string containing the parsed circuit data.

### Troubleshooting

- **"kicad-cli not found"**: The tool will still return component data but nets will be empty. Ensure KiCad 7.0+ is installed and `kicad-cli` is on the system PATH.
- **"No .kicad_pro file found"**: The `project_path` must point to a directory containing a `.kicad_pro` file, or directly to a `.kicad_sch` / `.kicad_pro` file.
- **Import errors**: Ensure you're using the venv Python (`<install-dir>/.venv/bin/python`), not the system Python.

## Running Tests

```bash
python -m unittest tests.test_pipeline -v
```

## Project Structure

```
├── main.py           CLI entry point
├── server.py         MCP server (FastMCP, stdio)
├── schematic.py      KiCad schematic parsing (kiutils)
├── netlist.py        Netlist generation (kicad-cli + XML parsing)
├── formatter.py      YAML output formatting
├── requirements.txt  Python dependencies
├── plan.md           Original system specification
└── tests/
    └── test_pipeline.py
```
