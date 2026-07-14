from __future__ import annotations

import time
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (Button, Checkbox, DataTable, Footer, Header, Input,
                             Label, OptionList, RichLog, SelectionList, Static)
from textual.widgets.option_list import Option
from textual.widgets.selection_list import Selection

from .discover import ForestInfo, list_deferred, list_forests, list_targets
from .plan import (CtestOpts, Selections, Step, build_steps, emit_plan_script,
                   forest_dir, prereq_closure)
from .runner import StepResult, run_step

NEW_FOREST = "__new__"


class ForestScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Select a forest (build environment)", classes="title")
        yield OptionList(id="forests")
        yield Input(placeholder="new forest suffix (e.g. pr6500)", id="new-suffix", disabled=True)
        yield Button("Next", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        ol = self.query_one("#forests", OptionList)
        for f in app.forests:
            name = f"build_forest{'-' + f.suffix if f.suffix else ''}"
            art = "ITK built" if f.itk_artifact else "no ITK artifact"
            desc = f"{name}  [{f.itk_branch} @ {f.itk_sha or '?'}  {f.itk_describe}]  {art}"
            ol.add_option(Option(desc, id=f.suffix or "__default__"))
        ol.add_option(Option("[ New forest… ]", id=NEW_FOREST))

    @on(OptionList.OptionSelected, "#forests")
    def _picked(self, ev: OptionList.OptionSelected) -> None:
        self.query_one("#new-suffix", Input).disabled = ev.option.id != NEW_FOREST
        self._choice = ev.option.id

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        choice = getattr(self, "_choice", None)
        if choice is None:
            self.notify("Pick a forest first", severity="warning")
            return
        if choice == NEW_FOREST:
            suffix = self.query_one("#new-suffix", Input).value.strip()
            if not suffix:
                self.notify("New forest needs a suffix", severity="warning")
                return
            app.sel.forest_suffix, app.sel.create_forest = suffix, True
        else:
            app.sel.forest_suffix = "" if choice == "__default__" else choice
            app.sel.create_forest = False
        app.push_screen(RefScreen())


class RefScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("ITK ref under test (pr/NNNN, remote/branch, tag, SHA)", classes="title")
        yield Input(placeholder="pr/6250 | upstream/main | v5.4.0 | <sha>", id="ref")
        yield Checkbox("Keep current checkout (skip repoint-itk)", id="keep")
        yield Button("Next", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        cur = next((f for f in app.forests if f.suffix == app.sel.forest_suffix), None)
        if cur and cur.itk_branch:
            self.query_one("#ref", Input).value = cur.itk_branch

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        if self.query_one("#keep", Checkbox).value:
            app.sel.itk_ref = ""
        else:
            ref = self.query_one("#ref", Input).value.strip()
            if not ref or (ref.startswith("pr/") and not ref[3:].isdigit()):
                self.notify("Invalid ref (pr/ needs digits; must be non-empty)", severity="error")
                return
            app.sel.itk_ref = ref
        app.push_screen(ProjectsScreen())


class ProjectsScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Projects to build (prerequisites auto-added)", classes="title")
        yield Checkbox("Full run-matrix.sh sweep instead (supersedes selections)", id="sweep")
        yield SelectionList[str](id="projects")
        yield Static("", id="deferred-note")
        yield Button("Next", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        sl = self.query_one("#projects", SelectionList)
        for t in app.targets:
            sl.add_option(Selection(t, t, initial_state=(t == "ITK")))
        note = "Deferred (known-broken, excluded): " + "; ".join(
            f"{n} — {r}" for n, r in app.deferred)
        self.query_one("#deferred-note", Static).update(note)

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        app.sel.full_matrix = self.query_one("#sweep", Checkbox).value
        picked = list(self.query_one("#projects", SelectionList).selected)
        app.sel.projects = prereq_closure(picked, app.targets) if picked else []
        if not app.sel.full_matrix and not app.sel.projects:
            self.notify("Select at least one project or the full sweep", severity="warning")
            return
        app.push_screen(TestsScreen())


class TestsScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Tests (artifact check always on)", classes="title")
        yield SelectionList[str](id="ctest-projects")
        yield Input(placeholder="CTEST_INCLUDE regex (optional)", id="include")
        yield Input(placeholder="per-test timeout seconds (default 300)", id="timeout")
        yield Button("Review plan", id="next", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        sl = self.query_one("#ctest-projects", SelectionList)
        if app.sel.full_matrix:
            sl.disabled = True
            self.query_one("#include", Input).placeholder = "CTEST_INCLUDE for the sweep (optional)"
        else:
            for t in app.sel.projects:
                sl.add_option(Selection(f"ctest {t}", t))

    @on(Button.Pressed, "#next")
    def _next(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        include = self.query_one("#include", Input).value.strip()
        tmo = self.query_one("#timeout", Input).value.strip()
        timeout = int(tmo) if tmo.isdigit() else 300
        app.sel.ctest = {t: CtestOpts(True, include, timeout)
                         for t in self.query_one("#ctest-projects", SelectionList).selected}
        app.push_screen(ConfirmScreen())


class ConfirmScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("", id="coords", classes="title")
        yield RichLog(id="plan", wrap=False, highlight=False)
        with Horizontal():
            yield Button("Run", id="run", variant="success")
            yield Button("Quit", id="quit", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        app.steps = build_steps(app.sel)
        script = emit_plan_script(app.sel, app.steps)
        forest = forest_dir(app.root, app.sel.forest_suffix)
        coords = f"Forest: {forest.name} | ITK: {app.sel.itk_ref or '(current checkout)'}"
        self.query_one("#coords", Label).update(coords)
        self.query_one("#plan", RichLog).write(script)
        logs = forest / "logs"
        try:
            logs.mkdir(parents=True, exist_ok=True)
            app.plan_path = logs / f"tui-plan-{time.strftime('%Y%m%d-%H%M%S')}.sh"
            app.plan_path.write_text(script)
            self.query_one("#plan", RichLog).write(f"\n# saved: {app.plan_path}")
        except OSError:
            app.plan_path = None

    @on(Button.Pressed, "#run")
    def _run(self) -> None:
        self.app.push_screen(RunScreen())

    @on(Button.Pressed, "#quit")
    def _quit(self) -> None:
        self.app.exit()


class RunScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield DataTable(id="status")
            yield RichLog(id="tail", max_lines=2000, wrap=False)
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#status", DataTable)
        t.add_columns(("step", "step"), ("state", "state"), ("detail", "detail"))
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        for s in app.steps:
            t.add_row(s.name, "queued", "", key=s.name)
        self._execute()

    @work(exclusive=True)
    async def _execute(self) -> None:
        app: ForestTuiApp = self.app  # type: ignore[assignment]
        table = self.query_one("#status", DataTable)
        tail = self.query_one("#tail", RichLog)
        forest = forest_dir(app.root, app.sel.forest_suffix)
        summary: list[str] = []
        abort = False
        for s in app.steps:
            if abort:
                table.update_cell(s.name, "state", "SKIP")
                summary.append(f"SKIP  {s.name}")
                continue
            table.update_cell(s.name, "state", "running")
            try:
                res: StepResult = await run_step(s, app.root, forest, lambda line: tail.write(line))
            except Exception as e:
                res = StepResult("FAIL", f"error: {e}", forest / "logs" / f"tui-{s.name}.log")
            table.update_cell(s.name, "state", res.status)
            table.update_cell(s.name, "detail", res.detail)
            summary.append(f"{res.status:4}  {s.name:24} {res.detail}")
            if s.target == "ITK" and s.kind == "build" and res.status == "FAIL":
                abort = True
                tail.write("ITK FAILED — aborting remaining steps")
        tail.write("\n==================== SUMMARY ====================")
        for line in summary:
            tail.write(line)
        if app.plan_path:
            tail.write(f"plan: {app.plan_path}")
        tail.write("press q to quit")


class ForestTuiApp(App[None]):
    BINDINGS = [("q", "quit", "Quit")]
    CSS = """
    .title { padding: 1; text-style: bold; }
    #status { height: 40%; }
    #tail { height: 1fr; border: solid $accent; }
    """

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.sel = Selections()
        self.steps: list[Step] = []
        self.plan_path: Path | None = None
        self.forests: list[ForestInfo] = list_forests(root)
        self.targets: list[str] = list_targets(root)
        self.deferred: list[tuple[str, str]] = list_deferred(root)

    def on_mount(self) -> None:
        self.push_screen(ForestScreen())
