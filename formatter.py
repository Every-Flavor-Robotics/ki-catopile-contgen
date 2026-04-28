import yaml


class OutputFormatter:
    def __init__(self, project_name: str, hierarchy: dict):
        self.project_name = project_name
        self.hierarchy = hierarchy

    def format(self) -> str:
        data = {
            "project_name": self.project_name,
            "hierarchy": self.hierarchy,
        }

        yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)

        return (
            "# KiCad to Atopile Conversion Context\n"
            "\n"
            f"This file contains the parsed hierarchical schematic data from the "
            f"KiCad project `{self.project_name}`. \n"
            f"Please use this YAML structure to generate the equivalent Atopile "
            f"(`.ato`) code. Map symbols and LCSC numbers to atopile components, "
            f"and map nets to atopile `~` connection statements.\n"
            "\n"
            "```yaml\n"
            f"{yaml_str}"
            "```\n"
        )
