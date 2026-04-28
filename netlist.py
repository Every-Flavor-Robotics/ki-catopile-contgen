import logging
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

logger = logging.getLogger(__name__)

KICAD_CLI_CANDIDATES = [
    "kicad-cli",
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
    "/usr/bin/kicad-cli",
    "/usr/local/bin/kicad-cli",
]


def _find_kicad_cli() -> str:
    for cmd in KICAD_CLI_CANDIDATES:
        try:
            result = subprocess.run(
                [cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.debug(f"Found kicad-cli at: {cmd}")
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise FileNotFoundError(
        "kicad-cli not found. KiCad 7.0+ must be installed and kicad-cli "
        "must be in your PATH to extract netlist data."
    )


class NetlistGenerator:
    def __init__(self, root_sch_path: Path):
        self.root_sch_path = root_sch_path

    def generate(self) -> dict:
        kicad_cli = _find_kicad_cli()

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix=".xml")
            os.close(fd)

            result = subprocess.run(
                [
                    kicad_cli, "sch", "export", "netlist",
                    "--format", "kicadxml",
                    "--output", tmp_path,
                    str(self.root_sch_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"kicad-cli netlist export failed (exit code {result.returncode}):\n"
                    f"{result.stderr}"
                )

            nets = self._parse_xml(tmp_path)
            logger.debug(f"Parsed {len(nets)} nets from XML netlist")
            return nets
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _parse_xml(self, xml_path: str) -> dict:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        nets = {}
        for net_elem in root.iter("net"):
            net_name = net_elem.attrib.get("name", "")
            if not net_name:
                continue

            connections = []
            for node in net_elem.findall("node"):
                ref = node.attrib.get("ref", "")
                pin = node.attrib.get("pin", "")
                if ref:
                    connections.append(f"{ref}.{pin}")

            if connections:
                nets[net_name] = connections

        return nets
