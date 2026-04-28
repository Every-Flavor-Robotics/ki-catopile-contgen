#!/usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path

from formatter import OutputFormatter
from netlist import NetlistGenerator
from schematic import SchematicParser


def find_root_schematic(input_path: Path) -> Path:
    if input_path.is_file():
        if input_path.suffix == ".kicad_sch":
            return input_path
        if input_path.suffix == ".kicad_pro":
            sch_path = input_path.with_suffix(".kicad_sch")
            if sch_path.exists():
                return sch_path
            raise FileNotFoundError(
                f"No .kicad_sch file found matching {input_path.name}"
            )
        raise ValueError(f"Unsupported file type: {input_path.suffix}")

    if input_path.is_dir():
        pro_files = list(input_path.glob("*.kicad_pro"))
        if not pro_files:
            raise FileNotFoundError(
                f"No .kicad_pro file found in {input_path}"
            )
        sch_path = pro_files[0].with_suffix(".kicad_sch")
        if not sch_path.exists():
            raise FileNotFoundError(
                f"No .kicad_sch file found matching {pro_files[0].name}"
            )
        return sch_path

    raise FileNotFoundError(f"Input path does not exist: {input_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract KiCad schematic data for Atopile conversion context."
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="Path to KiCad project directory, .kicad_sch, or .kicad_pro file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("./kicad-atopile-conversion-context.md"),
        help="Output file path (default: ./kicad-atopile-conversion-context.md)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress all output except fatal errors",
    )

    args = parser.parse_args()

    log_level = (
        logging.CRITICAL
        if args.quiet
        else (logging.DEBUG if args.verbose else logging.INFO)
    )
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")
    logger = logging.getLogger(__name__)

    try:
        root_sch = find_root_schematic(args.input_path.resolve())
        logger.debug(f"Root schematic: {root_sch}")

        project_name = root_sch.stem

        sch_parser = SchematicParser(root_sch)
        hierarchy = sch_parser.parse()
        logger.info(f"Parsed {len(hierarchy)} sheet(s)")

        netlist_gen = NetlistGenerator(root_sch)
        nets = netlist_gen.generate()
        logger.info(f"Extracted {len(nets)} net(s)")

        sch_parser.assign_nets(nets)

        formatter = OutputFormatter(project_name, hierarchy)
        output = formatter.format()

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        logger.info(f"Output written to {args.output}")

    except FileNotFoundError as e:
        logger.critical(str(e))
        sys.exit(1)
    except RuntimeError as e:
        logger.critical(str(e))
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
