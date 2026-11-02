#!/usr/bin/env python3
"""GnuChan Desktop panel for wallpaper and RandR display configuration."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION = "1.0.0"
APP_NAME = "GnuChan Desktop"
DEFAULT_CONFIG = Path.home() / ".config" / "gnuchan-desktop" / "panel.conf"
OUTPUT_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
MODE_NAME = re.compile(r"^[0-9]{1,5}x[0-9]{1,5}$")
ROTATIONS = {"normal", "left", "right", "inverted"}
WALLPAPER_MODES = {"fill", "fit", "center", "tile"}
COLOR_VALUE = re.compile(r"^#[0-9A-Fa-f]{6}$")
tk = None
filedialog = None
messagebox = None
ttk = None


def load_tkinter() -> None:
    global tk, filedialog, messagebox, ttk
    try:
        import tkinter as tk_module
        from tkinter import filedialog as filedialog_module
        from tkinter import messagebox as messagebox_module
        from tkinter import ttk as ttk_module
    except ImportError as exc:
        raise PanelError("Tkinter is not installed. Install your distribution's python3-tk package.") from exc
    tk, filedialog, messagebox, ttk = (
        tk_module, filedialog_module, messagebox_module, ttk_module
    )


class PanelError(Exception):
    """An expected, user-displayable configuration or system error."""


@dataclass
class Monitor:
    name: str
    connected: bool
    modes: list[str]
    enabled: bool = True
    mode: str = ""
    x: int = 0
    y: int = 0
    rotation: str = "normal"
    primary: bool = False


@dataclass
class Settings:
    wallpaper: str = ""
    wallpaper_mode: str = "fill"
    background_color: str = ""
    monitors: dict[str, Monitor] | None = None

    def __post_init__(self) -> None:
        if self.monitors is None:
            self.monitors = {}


def parse_config(text: str) -> Settings:
    """Parse strict Key=value settings; never evaluate config contents."""
    settings = Settings()
    seen: set[str] = set()
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise PanelError(f"Config line {line_number}: expected Key=value.")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key or key in seen:
            raise PanelError(f"Config line {line_number}: empty or duplicate key '{key}'.")
        seen.add(key)
        if key == "wallpaper":
            settings.wallpaper = value
        elif key == "background_color":
            if value and not COLOR_VALUE.fullmatch(value):
                raise PanelError(f"Config line {line_number}: background_color must be #RRGGBB.")
            settings.background_color = value
        elif key == "wallpaper_mode":
            if value not in WALLPAPER_MODES:
                raise PanelError(
                    f"Config line {line_number}: wallpaper_mode must be "
                    f"one of {', '.join(sorted(WALLPAPER_MODES))}."
                )
            settings.wallpaper_mode = value
        elif key.startswith("monitor."):
            name = key[len("monitor.") :]
            if not OUTPUT_NAME.fullmatch(name):
                raise PanelError(f"Config line {line_number}: invalid monitor name '{name}'.")
            fields = value.split(",")
            if len(fields) != 6:
                raise PanelError(
                    f"Config line {line_number}: monitor value must be "
                    "enabled,mode,x,y,rotation,primary."
                )
            enabled, mode, x_text, y_text, rotation, primary = fields
            if enabled not in {"on", "off"} or primary not in {"yes", "no"}:
                raise PanelError(f"Config line {line_number}: invalid monitor on/off or primary value.")
            if mode != "auto" and not MODE_NAME.fullmatch(mode):
                raise PanelError(f"Config line {line_number}: invalid resolution '{mode}'.")
            if rotation not in ROTATIONS:
                raise PanelError(f"Config line {line_number}: invalid rotation '{rotation}'.")
            try:
                x, y = int(x_text), int(y_text)
            except ValueError as exc:
                raise PanelError(f"Config line {line_number}: monitor positions must be integers.") from exc
            if not (-32768 <= x <= 32768 and -32768 <= y <= 32768):
                raise PanelError(f"Config line {line_number}: monitor positions must be between -32768 and 32768.")
            settings.monitors[name] = Monitor(
                name=name, connected=True, modes=[],
                enabled=enabled == "on", mode=mode, x=x, y=y,
                rotation=rotation, primary=primary == "yes",
            )
        else:
            raise PanelError(f"Config line {line_number}: unknown key '{key}'.")
    return settings


def serialize_config(settings: Settings) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in settings.wallpaper):
        raise PanelError("Wallpaper path contains unsupported control characters.")
    lines = [
        "# GnuChan Desktop panel settings (Key=value; do not put shell commands here).",
        f"wallpaper={settings.wallpaper}",
        f"background_color={settings.background_color}",
        f"wallpaper_mode={settings.wallpaper_mode}",
    ]
    for name in sorted(settings.monitors or {}):
        monitor = settings.monitors[name]
        lines.append(
            f"monitor.{name}={'on' if monitor.enabled else 'off'},"
            f"{monitor.mode or 'auto'},{monitor.x},{monitor.y},"
            f"{monitor.rotation},{'yes' if monitor.primary else 'no'}"
        )
    return "\n".join(lines) + "\n"


def read_config(path: Path) -> Settings:
    try:
        return parse_config(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except OSError as exc:
        raise PanelError(f"Cannot read config '{path}': {exc}") from exc
    except UnicodeError as exc:
        raise PanelError(f"Config '{path}' is not valid UTF-8.") from exc


def write_config(path: Path, settings: Settings) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".new")
        temporary.write_text(serialize_config(settings), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as exc:
        raise PanelError(f"Cannot save config '{path}': {exc}") from exc


def parse_xrandr_output(text: str) -> list[Monitor]:
    monitors: list[Monitor] = []
    current: Monitor | None = None
    for line in text.splitlines():
        match = re.match(r"^(\S+)\s+(connected|disconnected)\b(.*)$", line)
        if match:
            name, state, detail = match.groups()
            if not OUTPUT_NAME.fullmatch(name):
                current = None
                continue
            current = Monitor(name=name, connected=state == "connected", modes=[])
            if current.connected:
                geometry = re.search(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", detail)
                if geometry:
                    width, height, x, y = geometry.groups()
                    current.mode = f"{width}x{height}"
                    current.x, current.y = int(x), int(y)
                current.primary = bool(re.search(r"\bprimary\b", detail))
                rotation = re.search(r"\((normal|left|right|inverted)\b", detail)
                if rotation:
                    current.rotation = rotation.group(1)
            monitors.append(current)
            continue
        if current and current.connected:
            mode = re.match(r"^\s+(\d{1,5}x\d{1,5})\s+", line)
            if mode and mode.group(1) not in current.modes:
                current.modes.append(mode.group(1))
    return [monitor for monitor in monitors if monitor.connected]


def run_command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(arguments, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise PanelError(f"Required program '{arguments[0]}' was not found. Install xrandr/feh.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise PanelError(f"Command failed: {shlex.join(arguments)}" + (f"\n{detail}" if detail else "")) from exc
    except OSError as exc:
        raise PanelError(f"Cannot run '{arguments[0]}': {exc}") from exc


def query_monitors() -> list[Monitor]:
    result = run_command(["xrandr", "--query"])
    monitors = parse_xrandr_output(result.stdout)
    if not monitors:
        raise PanelError("xrandr did not report any connected monitors. Check the X11/RandR session.")
    return monitors


def merge_settings(monitors: list[Monitor], saved: Settings) -> list[Monitor]:
    saved_monitors = saved.monitors or {}
    for monitor in monitors:
        stored = saved_monitors.get(monitor.name)
        if stored:
            monitor.enabled = stored.enabled
            monitor.x, monitor.y = stored.x, stored.y
            monitor.rotation, monitor.primary = stored.rotation, stored.primary
            monitor.mode = stored.mode if stored.mode == "auto" or stored.mode in monitor.modes else monitor.mode
        if not monitor.mode and monitor.modes:
            monitor.mode = monitor.modes[0]
    return monitors


def validate_settings(settings: Settings, monitors: list[Monitor]) -> None:
    if settings.wallpaper_mode not in WALLPAPER_MODES:
        raise PanelError("Wallpaper mode must be fill, fit, center, or tile.")
    if settings.background_color and not COLOR_VALUE.fullmatch(settings.background_color):
        raise PanelError("Background color must be a hexadecimal #RRGGBB value.")
    if settings.wallpaper:
        if any(ord(character) < 32 or ord(character) == 127 for character in settings.wallpaper):
            raise PanelError("Wallpaper path contains unsupported control characters.")
        image = Path(settings.wallpaper).expanduser()
        if not image.is_file() or not os.access(image, os.R_OK):
            raise PanelError(f"Wallpaper image is not a readable file: {image}")
    enabled = [monitor for monitor in monitors if monitor.enabled]
    if not enabled:
        raise PanelError("Enable at least one connected monitor.")
    primary = [monitor for monitor in enabled if monitor.primary]
    if len(primary) != 1:
        raise PanelError("Select exactly one enabled primary monitor.")
    for monitor in monitors:
        if monitor.rotation not in ROTATIONS:
            raise PanelError(f"{monitor.name}: unsupported rotation '{monitor.rotation}'.")
        if monitor.enabled:
            if monitor.mode != "auto" and monitor.mode not in monitor.modes:
                raise PanelError(f"{monitor.name}: resolution {monitor.mode} is not available.")
            if monitor.mode != "auto" and not MODE_NAME.fullmatch(monitor.mode):
                raise PanelError(f"{monitor.name}: choose a valid resolution.")
            if not (-32768 <= monitor.x <= 32768 and -32768 <= monitor.y <= 32768):
                raise PanelError(f"{monitor.name}: positions must be between -32768 and 32768.")


def build_xrandr_command(monitors: list[Monitor]) -> list[str]:
    command = ["xrandr"]
    for monitor in monitors:
        command.extend(["--output", monitor.name])
        if not monitor.enabled:
            command.append("--off")
            continue
        if monitor.mode == "auto":
            command.append("--auto")
        else:
            command.extend(["--mode", monitor.mode])
        command.extend(["--pos", f"{monitor.x}x{monitor.y}", "--rotate", monitor.rotation])
        if monitor.primary:
            command.append("--primary")
    return command


def apply_settings(settings: Settings, monitors: list[Monitor]) -> None:
    validate_settings(settings, monitors)
    if settings.wallpaper and not shutil.which("feh"):
        raise PanelError("Wallpaper application requires feh; install it before applying settings.")
    if not settings.wallpaper and settings.background_color and not shutil.which("xsetroot"):
        raise PanelError("A solid background requires xsetroot; install it before applying settings.")
    run_command(build_xrandr_command(monitors))
    if settings.wallpaper:
        image = str(Path(settings.wallpaper).expanduser())
        feh_modes = {"fill": "--bg-fill", "fit": "--bg-max", "center": "--bg-center", "tile": "--bg-tile"}
        run_command(["feh", feh_modes[settings.wallpaper_mode], image])
    elif settings.background_color:
        run_command(["xsetroot", "-solid", settings.background_color])


class DesktopPanel:
    def __init__(self, root: tk.Tk, config_path: Path):
        self.root = root
        self.config_path = config_path
        self.settings = read_config(config_path)
        self.monitors: list[Monitor] = []
        self.rows: list[dict[str, object]] = []
        self._primary_choice = tk.IntVar(value=0)
        self.wallpaper_var = tk.StringVar(value=self.settings.wallpaper)
        self.background_color_var = tk.StringVar(value=self.settings.background_color)
        self.wallpaper_mode_var = tk.StringVar(value=self.settings.wallpaper_mode)
        root.title(f"{APP_NAME} {VERSION}")
        root.minsize(720, 340)
        self._build()
        self.refresh()

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="Display & wallpaper", font=("", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Refresh", command=self.refresh).pack(side="right")
        ttk.Label(outer, text="Wallpaper image").pack(anchor="w", pady=(14, 2))
        wallpaper = ttk.Frame(outer)
        wallpaper.pack(fill="x")
        ttk.Entry(wallpaper, textvariable=self.wallpaper_var).pack(side="left", fill="x", expand=True)
        ttk.Button(wallpaper, text="Browse…", command=self.browse_wallpaper).pack(side="left", padx=(6, 0))
        ttk.Label(wallpaper, text="Style").pack(side="left", padx=(12, 4))
        ttk.Combobox(
            wallpaper, textvariable=self.wallpaper_mode_var,
            values=sorted(WALLPAPER_MODES), state="readonly", width=9,
        ).pack(side="left")
        background = ttk.Frame(outer)
        background.pack(fill="x", pady=(5, 0))
        ttk.Label(background, text="Background color (when no image, #RRGGBB)").pack(side="left")
        ttk.Entry(background, textvariable=self.background_color_var, width=12).pack(side="left", padx=8)
        self.monitor_frame = ttk.LabelFrame(outer, text="Connected monitors", padding=8)
        self.monitor_frame.pack(fill="both", expand=True, pady=12)
        self.monitor_count = ttk.Label(self.monitor_frame, text="0 connected")
        self.monitor_count.pack(anchor="e")
        ttk.Label(
            self.monitor_frame,
            text="Enable    Resolution      X       Y       Rotation       Primary",
        ).pack(anchor="w")
        self.rows_frame = ttk.Frame(self.monitor_frame)
        self.rows_frame.pack(fill="both", expand=True)
        footer = ttk.Frame(outer)
        footer.pack(fill="x")
        ttk.Label(footer, text=f"Settings: {self.config_path}").pack(side="left")
        ttk.Button(footer, text="Apply and save", command=self.apply).pack(side="right")

    def browse_wallpaper(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose wallpaper",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"), ("All files", "*")],
        )
        if selected:
            self.wallpaper_var.set(selected)

    def refresh(self) -> None:
        try:
            self.monitors = merge_settings(query_monitors(), self.settings)
            self._draw_monitors()
        except PanelError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)

    def _draw_monitors(self) -> None:
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self.rows.clear()
        self.monitor_count.configure(text=f"{len(self.monitors)} connected")
        for index, monitor in enumerate(self.monitors):
            row = ttk.Frame(self.rows_frame)
            row.pack(fill="x", pady=2)
            enabled = tk.BooleanVar(value=monitor.enabled)
            mode = tk.StringVar(value=monitor.mode)
            x = tk.StringVar(value=str(monitor.x))
            y = tk.StringVar(value=str(monitor.y))
            rotation = tk.StringVar(value=monitor.rotation)
            ttk.Checkbutton(row, text=monitor.name, variable=enabled, width=17).pack(side="left")
            modes = monitor.modes or ([monitor.mode] if monitor.mode else [])
            ttk.Combobox(
                row, textvariable=mode, values=["auto", *modes],
                state="readonly", width=15,
            ).pack(side="left", padx=(2, 8))
            ttk.Entry(row, textvariable=x, width=7).pack(side="left", padx=2)
            ttk.Entry(row, textvariable=y, width=7).pack(side="left", padx=2)
            ttk.Combobox(row, textvariable=rotation, values=sorted(ROTATIONS), state="readonly", width=11).pack(side="left", padx=8)
            ttk.Radiobutton(
                row, text="Primary", variable=self._primary_var(index), value=index,
                command=lambda selected=index: self._select_primary(selected),
            ).pack(side="left")
            self.rows.append({
                "enabled": enabled, "mode": mode, "x": x, "y": y,
                "rotation": rotation,
            })
        self._primary_index = next((i for i, mon in enumerate(self.monitors) if mon.primary), 0)
        self._select_primary(self._primary_index)

    def _primary_var(self, index: int) -> tk.IntVar:
        return self._primary_choice

    def _select_primary(self, index: int) -> None:
        self._primary_index = index
        if hasattr(self, "_primary_choice"):
            self._primary_choice.set(index)

    def _collect(self) -> Settings:
        selected: list[Monitor] = []
        for index, (monitor, row) in enumerate(zip(self.monitors, self.rows)):
            try:
                x, y = int(str(row["x"].get())), int(str(row["y"].get()))
            except ValueError as exc:
                raise PanelError(f"{monitor.name}: positions must be whole numbers.") from exc
            selected.append(Monitor(
                name=monitor.name, connected=True, modes=monitor.modes,
                enabled=bool(row["enabled"].get()), mode=str(row["mode"].get()),
                x=x, y=y, rotation=str(row["rotation"].get()),
                primary=self._primary_choice.get() == index,
            ))
        return Settings(
            wallpaper=self.wallpaper_var.get().strip(),
            wallpaper_mode=self.wallpaper_mode_var.get(),
            background_color=self.background_color_var.get().strip(),
            monitors={m.name: m for m in selected},
        )

    def apply(self) -> None:
        try:
            settings = self._collect()
            validate_settings(settings, list(settings.monitors.values()))
            apply_settings(settings, list(settings.monitors.values()))
            write_config(self.config_path, settings)
            self.settings = settings
            messagebox.showinfo(APP_NAME, "Display and wallpaper settings applied and saved.", parent=self.root)
        except PanelError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Key=value config file")
    parser.add_argument("--check-config", action="store_true", help="validate config syntax without applying")
    parser.add_argument("--apply-saved", action="store_true", help="apply saved settings without opening the panel")
    args = parser.parse_args(argv)
    try:
        settings = read_config(args.config)
        if args.check_config:
            print(f"Config OK: {args.config}")
            return 0
        if args.apply_saved:
            monitors = merge_settings(query_monitors(), settings)
            apply_settings(settings, monitors)
            return 0
        load_tkinter()
        root = tk.Tk()
        DesktopPanel(root, args.config)
        root.mainloop()
        return 0
    except PanelError as exc:
        print(f"{APP_NAME}: {exc}", file=sys.stderr)
        return 2
    except tk.TclError as exc:
        print(f"{APP_NAME}: cannot open graphical panel: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
