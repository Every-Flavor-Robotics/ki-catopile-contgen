# System Specification: KiCad to Atopile Context Extractor

## 1. Project Overview
You are an autonomous coding agent tasked with building a standalone Python CLI tool. The goal of this tool is to parse a KiCad v6/v7/v8 project directory, extract the hierarchical schematic data (components, properties, instances, and nets), and output this data into a structured file. 

This output file will be used as the context window for an LLM to compile the KiCad circuit into an Atopile (`.ato`) project.

## 2. Technical Stack
* **Language**: Python 3.10+
* **CLI Framework**: Python built-in `argparse`. Do not use external CLI frameworks.
* **KiCad File Parsing**: Use the `kiutils` library (`pip install kiutils`) to parse `.kicad_sch` files for component data and sheet hierarchy.
* **Netlist Parsing**: Built-in `xml.etree.ElementTree` and `subprocess`.

## 3. CLI Interface Requirements
**Command Structure:**
`python main.py [INPUT_PATH] [OPTIONS]`

**Positional Arguments:**
* `input_path`: (Required) The path to the KiCad project. The tool must accept either the project directory path OR the path to the root `.kicad_sch` / `.kicad_pro` file.

**Optional Flags:**
* `-o, --output`: Specifies the output file path. Default: `./kicad-atopile-conversion-context.md`
* `-v, --verbose`: Enables debug logging (e.g., printing parsed component counts, netlist status, or sub-sheet names).
* `-q, --quiet`: Suppresses all console output except fatal errors.

## 4. Data Extraction Requirements
The tool must find the root `.kicad_sch` file and traverse the hierarchical sheets. For each sheet, extract:

1. **Components (Symbols)**:
   * Reference Designator (e.g., `R1`, `C2`, `U1`)
   * Value (e.g., `10k`, `100nF`, `ESP32`)
   * Footprint (e.g., `Resistor_SMD:R_0402_1005Metric`)
   * LCSC Part Number (Extract this from the custom properties/fields of the symbol, often named `LCSC`, `LCSC Part`, or `LCSC Part #`).
2. **Sub-sheet Instances**:
   * Sheet Name / Instance Name
   * The file path of the sub-sheet being referenced.

## 5. Netlist Generation Strategy (CRITICAL)
Do NOT attempt to write a custom spatial intersection algorithm to calculate nets from raw `.kicad_sch` files. Instead, utilize the official KiCad CLI to generate an intermediate XML netlist, and parse the resulting XML to get accurate net connections.
1. Use Python's `subprocess` to execute: 
   `kicad-cli sch export netlist --format kicadxml --output temp_netlist.xml <path_to_root_schematic>`
2. Parse `temp_netlist.xml` using `xml.etree.ElementTree`. Extract the `<nets>` nodes to map net names to their connected component references and pins (e.g., Net `GND` connects to `R1.2`, `C1.2`).
3. Delete `temp_netlist.xml` via python after parsing is complete.
4. Handle Errors: If `kicad-cli` is not found on the system path or fails, gracefully catch the error and exit, informing the user that KiCad 7.0+ must be installed and in the PATH to extract nets.

## 6. Output Format
The tool must write a Markdown file (default name: `kicad-atopile-conversion-context.md`). The file must contain the following exact text preamble, followed by the JSON block payload.

**Output Template:**
# KiCad to Atopile Conversion Context

This file contains the parsed hierarchical schematic data from the KiCad project `{Project Name}`. 
Please use this JSON structure to generate the equivalent Atopile (`.ato`) code. Map symbols and LCSC numbers to atopile components, and map nets to atopile `~` connection statements.

\`\`\`json
{
  "project_name": "{Project Name}",
  "hierarchy": {
    "{Sheet_Name}": {
      "components": [
        {
          "designator": "R1",
          "value": "10k",
          "footprint": "Resistor_SMD...",
          "lcsc_part": "C12345"
        }
      ],
      "sub_sheets": [
        {
          "instance_name": "motor_driver_1",
          "sheet_file": "DRV8825.kicad_sch"
        }
      ],
      "nets": {
        "GND": ["R1.2", "motor_driver_1.GND"],
        "VDD": ["R1.1"]
      }
    }
  }
}
\`\`\`

## 7. Implementation Plan
Follow these steps strictly:
1. **Scaffolding**: Initialize the project, setup `argparse`, and validate the `input_path` exists.
2. **KiCad-CLI Netlist**: Implement the subprocess call to `kicad-cli` to generate and parse the XML netlist. Extract all valid nets and their pin connections.
3. **Schematic Parsing**: Use `kiutils` to parse the root `.kicad_sch` file. Extract Symbols (checking properties for LCSC numbers) and hierarchical Sheets.
4. **Hierarchy Traversal**: Recursively parse referenced sub-sheets found in step 3 to build the full "hierarchy" dictionary. Cross-reference with the parsed netlist to assign nets to the correct sheet context.
5. **Formatting & Output**: Aggregate all extracted data into the required JSON schema, wrap it in the Markdown template, and write it to disk.
6. **Testing**: Write a minimal mock `.kicad_sch` file using `kiutils` (or just dummy text generation) to test your CLI's output logic locally before finalizing the code.