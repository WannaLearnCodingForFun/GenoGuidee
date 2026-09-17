"""python -m genoguide [doctor|regression-test|demo-regression|…legacy commands]"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (str(REPO), str(REPO / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        from cli.genoguide import main as cli_main
        return cli_main(["--help"])
    cmd = args[0]
    if cmd == "doctor":
        from cli.commands import doctor_cmd
        return doctor_cmd.run()
    if cmd == "regression-test":
        from cli.commands import regression_cmd
        return regression_cmd.run()
    if cmd == "demo-regression":
        from cli.commands import demo_regression_cmd
        return demo_regression_cmd.run()
    from cli.genoguide import main as cli_main
    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
