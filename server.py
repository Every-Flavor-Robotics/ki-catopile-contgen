from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

from main import find_root_schematic
from netlist import NetlistGenerator
from schematic import SchematicParser

mcp = FastMCP("KiCad Atopile Extractor")


@mcp.tool()
def parse_kicad_project(project_path: str) -> str:
    """
    Extracts component data and hierarchical netlists from a KiCad schematic
    project directory. Returns an optimized YAML representation of the circuit
    to be used for atopile conversion.
    """
    root_sch = find_root_schematic(Path(project_path).resolve())
    project_name = root_sch.stem

    sch_parser = SchematicParser(root_sch)
    hierarchy = sch_parser.parse()

    netlist_gen = NetlistGenerator(root_sch)
    nets = netlist_gen.generate()

    sch_parser.assign_nets(nets)

    data = {
        "project_name": project_name,
        "hierarchy": hierarchy,
    }

    return yaml.dump(data, default_flow_style=False, sort_keys=False)


if __name__ == "__main__":
    mcp.run()
