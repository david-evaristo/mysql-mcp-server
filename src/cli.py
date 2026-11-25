"""Console entry point — installed as `mysql-mcp-server` (see [project.scripts] in pyproject.toml)."""
from src.initialization import mcp
from src.logging_config import configure_logging


def main() -> None:
    configure_logging()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
