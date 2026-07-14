from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .discover import list_targets, testbed_root
from .plan import CtestOpts, Selections, build_steps, emit_plan_script, prereq_closure


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="forest_tui")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--forest", default=None, help="forest suffix; '' for default build_forest")
    p.add_argument("--new-forest", action="store_true")
    p.add_argument("--ref", default="")
    p.add_argument("--projects", default="")
    p.add_argument("--full-matrix", action="store_true")
    p.add_argument("--ctest", default="")
    p.add_argument("--ctest-include", default="")
    return p.parse_args(argv)


def selections_from_args(a: argparse.Namespace, root: Path) -> Selections:
    projects = [t for t in a.projects.split(",") if t]
    if projects:
        projects = prereq_closure(projects, list_targets(root))
    ctest = {t: CtestOpts(True, a.ctest_include) for t in a.ctest.split(",") if t}
    return Selections(a.forest or "", a.new_forest, a.ref, a.full_matrix, projects, ctest,
                      root=str(testbed_root(root)))


def main(argv: list[str] | None = None) -> int:
    a = parse_args(sys.argv[1:] if argv is None else argv)
    root = Path.cwd()
    if a.dry_run:
        sel = selections_from_args(a, root)
        sys.stdout.write(emit_plan_script(sel, build_steps(sel)))
        return 0
    from .app import ForestTuiApp
    ForestTuiApp(root).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
