import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml

from formatter import OutputFormatter
from netlist import NetlistGenerator, _find_kicad_cli
from schematic import SchematicParser, LCSC_FIELD_NAMES
from main import find_root_schematic


MOCK_NETLIST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<export version="D">
  <design>
    <source>test.kicad_sch</source>
    <date>2026-04-27</date>
    <tool>Eeschema test</tool>
  </design>
  <components>
    <comp ref="R1">
      <value>10k</value>
      <footprint>Resistor_SMD:R_0402_1005Metric</footprint>
      <sheetpath names="/" tstamps="/"/>
    </comp>
    <comp ref="C1">
      <value>100nF</value>
      <footprint>Capacitor_SMD:C_0402_1005Metric</footprint>
      <sheetpath names="/" tstamps="/"/>
    </comp>
    <comp ref="U1">
      <value>ESP32</value>
      <footprint>RF_Module:ESP32-WROOM-32</footprint>
      <sheetpath names="/power/" tstamps="/abc/"/>
    </comp>
  </components>
  <nets>
    <net code="1" name="GND">
      <node ref="R1" pin="2" pintype="passive"/>
      <node ref="C1" pin="2" pintype="passive"/>
      <node ref="U1" pin="GND" pintype="power_in"/>
    </net>
    <net code="2" name="VDD">
      <node ref="R1" pin="1" pintype="passive"/>
      <node ref="U1" pin="VCC" pintype="power_in"/>
    </net>
    <net code="3" name="unconnected-(C1-Pad1)">
      <node ref="C1" pin="1" pintype="passive"/>
    </net>
  </nets>
</export>
"""


def _create_minimal_kicad_sch(path: Path, components=None, sheets=None):
    from kiutils.schematic import Schematic
    from kiutils.items.schitems import SchematicSymbol, HierarchicalSheet, HierarchicalPin
    from kiutils.items.common import Property

    sch = Schematic.create_new()

    if components:
        for comp in components:
            props = [
                Property(key="Reference", value=comp["ref"]),
                Property(key="Value", value=comp.get("value", "")),
            ]
            if "footprint" in comp:
                props.append(Property(key="Footprint", value=comp["footprint"]))
            if "lcsc" in comp:
                props.append(Property(key="LCSC", value=comp["lcsc"]))

            lib_id = comp.get("lib_id", "Device:R")
            lib_nick, entry = (lib_id.split(":", 1) + [""])[:2]
            sym = SchematicSymbol(libraryNickname=lib_nick, entryName=entry)
            sym.properties = props
            sch.schematicSymbols.append(sym)

    if sheets:
        for sheet_info in sheets:
            h_pins = []
            for pin_name in sheet_info.get("pins", []):
                h_pins.append(
                    HierarchicalPin(
                        name=pin_name,
                        connectionType="bidirectional",
                    )
                )

            hs = HierarchicalSheet(
                sheetName=Property(
                    key="Sheetname",
                    value=sheet_info["name"],
                ),
                fileName=Property(
                    key="Sheetfile",
                    value=sheet_info["file"],
                ),
            )
            hs.pins = h_pins
            sch.sheets.append(hs)

    sch.to_file(str(path))
    return path


def _parse_yaml_output(output: str) -> dict:
    yaml_start = output.index("```yaml\n") + len("```yaml\n")
    yaml_end = output.index("\n```", yaml_start)
    return yaml.safe_load(output[yaml_start:yaml_end])


class TestOutputFormatter(unittest.TestCase):
    def test_basic_format(self):
        hierarchy = {
            "root": {
                "components": {
                    "R1": ["10k", "Resistor_SMD:R_0402_1005Metric", "C12345"],
                },
                "sub_sheets": [],
                "nets": {"GND": ["R1.2"]},
            }
        }
        fmt = OutputFormatter("test_project", hierarchy)
        output = fmt.format()

        self.assertIn("# KiCad to Atopile Conversion Context", output)
        self.assertIn("`test_project`", output)
        self.assertIn("```yaml", output)

        data = _parse_yaml_output(output)

        self.assertEqual(data["project_name"], "test_project")
        self.assertIn("root", data["hierarchy"])
        self.assertIn("R1", data["hierarchy"]["root"]["components"])
        self.assertEqual(
            data["hierarchy"]["root"]["components"]["R1"],
            ["10k", "Resistor_SMD:R_0402_1005Metric", "C12345"],
        )
        self.assertEqual(data["hierarchy"]["root"]["nets"]["GND"], ["R1.2"])

    def test_empty_hierarchy(self):
        fmt = OutputFormatter("empty_project", {})
        output = fmt.format()
        data = _parse_yaml_output(output)
        self.assertEqual(data["hierarchy"], {})

    def test_multiple_sheets(self):
        hierarchy = {
            "top": {
                "components": {"R1": ["1k", ""]},
                "sub_sheets": [{"instance_name": "sub", "sheet_file": "sub.kicad_sch"}],
                "nets": {"VCC": ["R1.1", "sub.VCC"]},
            },
            "sub": {
                "components": {"C1": ["100nF", ""]},
                "sub_sheets": [],
                "nets": {"VCC": ["C1.1"]},
            },
        }
        fmt = OutputFormatter("multi_sheet", hierarchy)
        output = fmt.format()
        data = _parse_yaml_output(output)
        self.assertIn("top", data["hierarchy"])
        self.assertIn("sub", data["hierarchy"])
        self.assertEqual(data["hierarchy"]["top"]["nets"]["VCC"], ["R1.1", "sub.VCC"])


class TestNetlistParser(unittest.TestCase):
    def test_parse_xml(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(MOCK_NETLIST_XML)
            tmp_path = f.name

        try:
            gen = NetlistGenerator(Path("/dummy.kicad_sch"))
            nets = gen._parse_xml(tmp_path)

            self.assertIn("GND", nets)
            self.assertIn("VDD", nets)
            self.assertIn("unconnected-(C1-Pad1)", nets)

            self.assertEqual(set(nets["GND"]), {"R1.2", "C1.2", "U1.GND"})
            self.assertEqual(set(nets["VDD"]), {"R1.1", "U1.VCC"})
            self.assertEqual(nets["unconnected-(C1-Pad1)"], ["C1.1"])
        finally:
            os.unlink(tmp_path)

    def test_find_kicad_cli_not_found(self):
        with patch("netlist.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                _find_kicad_cli()


class TestSchematicParser(unittest.TestCase):
    def test_parse_single_sheet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_path = Path(tmpdir) / "test.kicad_sch"
            _create_minimal_kicad_sch(
                sch_path,
                components=[
                    {"ref": "R1", "value": "10k", "footprint": "Resistor_SMD:R_0402", "lcsc": "C123"},
                    {"ref": "C1", "value": "100nF", "footprint": "Capacitor_SMD:C_0402"},
                ],
            )

            parser = SchematicParser(sch_path)
            hierarchy = parser.parse()

            self.assertIn("test", hierarchy)
            comps = hierarchy["test"]["components"]
            self.assertEqual(len(comps), 2)
            self.assertIn("R1", comps)
            self.assertIn("C1", comps)
            self.assertEqual(comps["R1"], ["10k", "Resistor_SMD:R_0402", "C123"])
            self.assertEqual(comps["C1"], ["100nF", "Capacitor_SMD:C_0402"])
            self.assertEqual(hierarchy["test"]["sub_sheets"], [])

    def test_parse_with_sub_sheet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_path = Path(tmpdir) / "motor_driver.kicad_sch"
            _create_minimal_kicad_sch(
                sub_path,
                components=[
                    {"ref": "U1", "value": "DRV8825", "footprint": "Package_SO:TSSOP-24"},
                ],
            )

            root_path = Path(tmpdir) / "root.kicad_sch"
            _create_minimal_kicad_sch(
                root_path,
                components=[
                    {"ref": "R1", "value": "10k"},
                ],
                sheets=[
                    {
                        "name": "motor_driver",
                        "file": "motor_driver.kicad_sch",
                        "pins": ["GND", "VCC"],
                    },
                ],
            )

            parser = SchematicParser(root_path)
            hierarchy = parser.parse()

            self.assertIn("root", hierarchy)
            self.assertIn("motor_driver", hierarchy)
            self.assertEqual(len(hierarchy["root"]["components"]), 1)
            self.assertEqual(len(hierarchy["motor_driver"]["components"]), 1)
            self.assertEqual(len(hierarchy["root"]["sub_sheets"]), 1)
            self.assertEqual(hierarchy["root"]["sub_sheets"][0]["instance_name"], "motor_driver")

    def test_filter_power_symbols(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_path = Path(tmpdir) / "test.kicad_sch"
            _create_minimal_kicad_sch(
                sch_path,
                components=[
                    {"ref": "R1", "value": "10k"},
                    {"ref": "#PWR001", "value": "GND"},
                    {"ref": "#FLG001", "value": "PWR_FLAG"},
                ],
            )

            parser = SchematicParser(sch_path)
            hierarchy = parser.parse()

            comps = hierarchy["test"]["components"]
            self.assertEqual(len(comps), 1)
            self.assertIn("R1", comps)

    def test_assign_nets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_path = Path(tmpdir) / "sub.kicad_sch"
            _create_minimal_kicad_sch(
                sub_path,
                components=[{"ref": "U1", "value": "Driver"}],
            )

            root_path = Path(tmpdir) / "root.kicad_sch"
            _create_minimal_kicad_sch(
                root_path,
                components=[{"ref": "R1", "value": "10k"}],
                sheets=[
                    {"name": "sub", "file": "sub.kicad_sch", "pins": ["GND"]},
                ],
            )

            parser = SchematicParser(root_path)
            parser.parse()

            nets = {
                "GND": ["R1.2", "U1.GND"],
                "VDD": ["R1.1"],
            }
            parser.assign_nets(nets)

            root_nets = parser.hierarchy["root"]["nets"]
            self.assertIn("GND", root_nets)
            self.assertIn("R1.2", root_nets["GND"])
            self.assertIn("sub.GND", root_nets["GND"])
            self.assertIn("VDD", root_nets)
            self.assertEqual(root_nets["VDD"], ["R1.1"])

            sub_nets = parser.hierarchy["sub"]["nets"]
            self.assertIn("GND", sub_nets)
            self.assertIn("U1.GND", sub_nets["GND"])

    def test_unconnected_nets_filtered(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_path = Path(tmpdir) / "test.kicad_sch"
            _create_minimal_kicad_sch(
                sch_path,
                components=[{"ref": "R1", "value": "10k"}],
            )

            parser = SchematicParser(sch_path)
            parser.parse()

            nets = {
                "GND": ["R1.2"],
                "unconnected-(R1-Pad1)": ["R1.1"],
                "unconnected-(C1-Pad3)": ["C1.3"],
            }
            parser.assign_nets(nets)

            sheet_nets = parser.hierarchy["test"]["nets"]
            self.assertIn("GND", sheet_nets)
            self.assertNotIn("unconnected-(R1-Pad1)", sheet_nets)
            self.assertNotIn("unconnected-(C1-Pad3)", sheet_nets)

    def test_ref_to_sheet_mapping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sub_path = Path(tmpdir) / "sub.kicad_sch"
            _create_minimal_kicad_sch(
                sub_path,
                components=[{"ref": "C1", "value": "100nF"}],
            )

            root_path = Path(tmpdir) / "root.kicad_sch"
            _create_minimal_kicad_sch(
                root_path,
                components=[{"ref": "R1", "value": "10k"}],
                sheets=[{"name": "sub", "file": "sub.kicad_sch"}],
            )

            parser = SchematicParser(root_path)
            parser.parse()

            self.assertEqual(parser.ref_to_sheet["R1"], "root")
            self.assertEqual(parser.ref_to_sheet["C1"], "sub")

    def test_lcsc_field_variants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_path = Path(tmpdir) / "test.kicad_sch"

            from kiutils.schematic import Schematic
            from kiutils.items.schitems import SchematicSymbol
            from kiutils.items.common import Property

            sch = Schematic.create_new()

            for field_name in LCSC_FIELD_NAMES:
                sym = SchematicSymbol(libraryNickname="Device", entryName="R")
                sym.properties = [
                    Property(key="Reference", value=f"R_{field_name}"),
                    Property(key="Value", value="1k"),
                    Property(key=field_name, value="C99999"),
                ]
                sch.schematicSymbols.append(sym)

            sch.to_file(str(sch_path))

            parser = SchematicParser(sch_path)
            hierarchy = parser.parse()

            comps = hierarchy["test"]["components"]
            for ref, props in comps.items():
                self.assertEqual(len(props), 3)
                self.assertEqual(props[2], "C99999", f"LCSC not found for {ref}")

    def test_no_lcsc_omits_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_path = Path(tmpdir) / "test.kicad_sch"
            _create_minimal_kicad_sch(
                sch_path,
                components=[
                    {"ref": "R1", "value": "10k", "footprint": "Resistor_SMD:R_0402"},
                ],
            )

            parser = SchematicParser(sch_path)
            hierarchy = parser.parse()

            props = hierarchy["test"]["components"]["R1"]
            self.assertEqual(len(props), 2)
            self.assertEqual(props, ["10k", "Resistor_SMD:R_0402"])

    def test_with_lcsc_has_three_elements(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_path = Path(tmpdir) / "test.kicad_sch"
            _create_minimal_kicad_sch(
                sch_path,
                components=[
                    {"ref": "R1", "value": "10k", "footprint": "Resistor_SMD:R_0402", "lcsc": "C555"},
                ],
            )

            parser = SchematicParser(sch_path)
            hierarchy = parser.parse()

            props = hierarchy["test"]["components"]["R1"]
            self.assertEqual(len(props), 3)
            self.assertEqual(props, ["10k", "Resistor_SMD:R_0402", "C555"])

    def test_invalid_lcsc_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_path = Path(tmpdir) / "test.kicad_sch"

            from kiutils.schematic import Schematic
            from kiutils.items.schitems import SchematicSymbol
            from kiutils.items.common import Property

            sch = Schematic.create_new()
            invalid_values = ["DNP", "-", "N/A", "~", "https://example.com", "C", "12345", "CC123"]
            for i, val in enumerate(invalid_values):
                sym = SchematicSymbol(libraryNickname="Device", entryName="R")
                sym.properties = [
                    Property(key="Reference", value=f"R{i}"),
                    Property(key="Value", value="1k"),
                    Property(key="LCSC", value=val),
                ]
                sch.schematicSymbols.append(sym)

            sch.to_file(str(sch_path))

            parser = SchematicParser(sch_path)
            hierarchy = parser.parse()

            for ref, props in hierarchy["test"]["components"].items():
                self.assertEqual(len(props), 2, f"{ref} should have no LCSC, got {props}")

    def test_valid_lcsc_patterns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_path = Path(tmpdir) / "test.kicad_sch"

            from kiutils.schematic import Schematic
            from kiutils.items.schitems import SchematicSymbol
            from kiutils.items.common import Property

            sch = Schematic.create_new()
            valid_values = ["C1", "C12345", "C999999999"]
            for val in valid_values:
                sym = SchematicSymbol(libraryNickname="Device", entryName="R")
                sym.properties = [
                    Property(key="Reference", value=f"R_{val}"),
                    Property(key="Value", value="1k"),
                    Property(key="LCSC", value=val),
                ]
                sch.schematicSymbols.append(sym)

            sch.to_file(str(sch_path))

            parser = SchematicParser(sch_path)
            hierarchy = parser.parse()

            for ref, props in hierarchy["test"]["components"].items():
                self.assertEqual(len(props), 3, f"{ref} should have LCSC, got {props}")
                self.assertTrue(props[2].startswith("C"), f"LCSC should start with C, got {props[2]}")


class TestFindRootSchematic(unittest.TestCase):
    def test_directory_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pro_path = Path(tmpdir) / "myproject.kicad_pro"
            sch_path = Path(tmpdir) / "myproject.kicad_sch"
            pro_path.touch()
            sch_path.touch()

            result = find_root_schematic(Path(tmpdir))
            self.assertEqual(result, sch_path)

    def test_sch_file_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sch_path = Path(tmpdir) / "myproject.kicad_sch"
            sch_path.touch()

            result = find_root_schematic(sch_path)
            self.assertEqual(result, sch_path)

    def test_pro_file_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pro_path = Path(tmpdir) / "myproject.kicad_pro"
            sch_path = Path(tmpdir) / "myproject.kicad_sch"
            pro_path.touch()
            sch_path.touch()

            result = find_root_schematic(pro_path)
            self.assertEqual(result, sch_path)

    def test_pro_without_sch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pro_path = Path(tmpdir) / "myproject.kicad_pro"
            pro_path.touch()

            with self.assertRaises(FileNotFoundError):
                find_root_schematic(pro_path)

    def test_nonexistent_path(self):
        with self.assertRaises(FileNotFoundError):
            find_root_schematic(Path("/nonexistent/path"))

    def test_unsupported_file_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_path = Path(tmpdir) / "test.txt"
            txt_path.touch()

            with self.assertRaises(ValueError):
                find_root_schematic(txt_path)


class TestLCSCFieldNames(unittest.TestCase):
    def test_expected_fields(self):
        expected = {"LCSC", "LCSC Part", "LCSC Part #", "JLCPCB", "JLCPCB Part #"}
        self.assertEqual(LCSC_FIELD_NAMES, expected)


class TestMCPServer(unittest.TestCase):
    def test_server_imports(self):
        import server
        self.assertTrue(hasattr(server, "mcp"))
        self.assertEqual(server.mcp.name, "KiCad Atopile Extractor")

    def test_tool_registered(self):
        import server
        tools = server.mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        self.assertIn("parse_kicad_project", names)

    def test_tool_schema(self):
        import server
        tools = server.mcp._tool_manager.list_tools()
        tool = next(t for t in tools if t.name == "parse_kicad_project")
        self.assertIn("project_path", tool.parameters["properties"])
        self.assertIn("project_path", tool.parameters.get("required", []))


if __name__ == "__main__":
    unittest.main()
