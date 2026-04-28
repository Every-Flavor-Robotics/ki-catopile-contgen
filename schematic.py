import logging
import re
from pathlib import Path

from kiutils.schematic import Schematic

logger = logging.getLogger(__name__)

LCSC_FIELD_NAMES = {"LCSC", "LCSC Part", "LCSC Part #", "JLCPCB", "JLCPCB Part #"}
LCSC_PATTERN = re.compile(r"^C\d+$")


class SchematicParser:
    def __init__(self, root_sch_path: Path):
        self.root_sch_path = root_sch_path
        self.hierarchy = {}
        self.ref_to_sheet = {}
        self.sheet_hierarchical_pins = {}

    def parse(self) -> dict:
        self._parse_sheet(self.root_sch_path, self.root_sch_path.stem)
        return self.hierarchy

    def _parse_sheet(self, sch_path: Path, sheet_name: str):
        logger.debug(f"Parsing sheet: {sch_path} as '{sheet_name}'")
        sch = Schematic.from_file(str(sch_path))

        components = {}
        sub_sheets = []
        h_pins = {}

        for sym in sch.schematicSymbols:
            ref, props = self._extract_component(sym)
            if ref and not ref.startswith("#"):
                components[ref] = props
                self.ref_to_sheet[ref] = sheet_name

        for sheet in sch.sheets:
            sub_name = sheet.sheetName.value
            sub_file = sheet.fileName.value
            pin_names = [pin.name for pin in sheet.pins]

            sub_sheets.append({
                "instance_name": sub_name,
                "sheet_file": sub_file,
            })
            h_pins[sub_name] = pin_names

            sub_path = sch_path.parent / sub_file
            if sub_path.exists():
                self._parse_sheet(sub_path, sub_name)
            else:
                logger.warning(f"Sub-sheet file not found: {sub_path}")

        self.sheet_hierarchical_pins[sheet_name] = h_pins
        self.hierarchy[sheet_name] = {
            "components": components,
            "sub_sheets": sub_sheets,
            "nets": {},
        }
        logger.debug(
            f"Sheet '{sheet_name}': {len(components)} components, "
            f"{len(sub_sheets)} sub-sheets"
        )

    def _extract_component(self, sym) -> tuple:
        props = {p.key: p.value for p in sym.properties}

        ref = props.get("Reference", "")
        value = props.get("Value", "")
        footprint = props.get("Footprint", "")

        lcsc = ""
        for field_name in LCSC_FIELD_NAMES:
            val = props.get(field_name, "")
            if val and LCSC_PATTERN.match(val):
                lcsc = val
                break

        result = [value, footprint]
        if lcsc:
            result.append(lcsc)

        return ref, result

    def assign_nets(self, nets: dict):
        for sheet_name, sheet_data in self.hierarchy.items():
            sheet_nets = {}
            sub_sheet_names = {
                ss["instance_name"] for ss in sheet_data["sub_sheets"]
            }
            h_pins = self.sheet_hierarchical_pins.get(sheet_name, {})

            for net_name, connections in nets.items():
                if net_name.startswith("unconnected-"):
                    continue

                sheet_connections = []
                sub_sheet_has_net = set()

                for conn in connections:
                    parts = conn.split(".", 1)
                    ref = parts[0]

                    if ref not in self.ref_to_sheet:
                        continue

                    ref_sheet = self.ref_to_sheet[ref]
                    if ref_sheet == sheet_name:
                        sheet_connections.append(conn)
                    elif ref_sheet in sub_sheet_names:
                        sub_sheet_has_net.add(ref_sheet)

                for ss_name in sub_sheet_has_net:
                    pins = h_pins.get(ss_name, [])
                    if net_name in pins:
                        sheet_connections.append(f"{ss_name}.{net_name}")

                if sheet_connections:
                    sheet_nets[net_name] = sheet_connections

            sheet_data["nets"] = sheet_nets
            logger.debug(f"Sheet '{sheet_name}': {len(sheet_nets)} nets assigned")
