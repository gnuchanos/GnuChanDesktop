# GnuChan Desktop

A small Tk desktop settings panel for wallpaper and X11 monitor configuration.
It uses `xrandr` for connected-output discovery, resolutions, monitor count,
layout positions, rotation, and primary selection. Wallpaper rendering follows
GnuChanWM's root-window/feh-style scaled wallpaper prior art and uses `feh`
(`--bg-fill` by default); a solid `#RRGGBB` background uses `xsetroot` when no
image is selected. Openbox itself does not set wallpaper.

## Requirements

- Linux / WSL with an X11 desktop session and RandR support
- Python 3.10+ with Tkinter
- `xrandr`
- `feh` to apply a non-empty wallpaper path
- `xsetroot` to apply a solid background color when no wallpaper is set

The panel calls external programs with argument arrays (never a shell), validates
config and monitor names, and reports missing programs, invalid selections, and
RandR failures. A wallpaper path is treated as a filename, not a command.

## Build and configuration tests

Run inside WSL/Linux from this repository:

```sh
./build.sh
```

The script compiles Python source, runs configuration/parser and RandR tests, and
validates the example `.conf`. No package install is required to run these tests.

## Install / launch

```sh
sudo ./install.sh
```

The script installs the panel as both `gnuchan-desktop-panel` and
`GnuChanDesktop` under `/usr/local/bin`; its desktop entry goes under
`/usr/share/applications` so GnuChanRunner and the desktop menu can discover it.
Launch **GnuChan Desktop** from the applications menu or run either command.
Select a wallpaper image and style, then configure each connected monitor's
enable state, resolution, X/Y position, rotation, and primary status. Apply and
save commits the xrandr layout, applies wallpaper if selected, and persists the
settings. The installer normalizes the installed launcher and desktop entry so
Windows checkouts with CRLF line endings still produce runnable commands and a
discoverable menu item.

For distribution packaging, `PREFIX`, `APP_DIR`, and `DESTDIR` can override
install paths: `PREFIX=/usr APP_DIR=/usr/share/applications
DESTDIR="$pkgdir" ./install.sh`.

## Config and login startup

Settings live in `~/.config/gnuchan-desktop/panel.conf`; the file is plain
`Key=value` with comments. `wallpaper` is an image path, `background_color` is
an optional `#RRGGBB` color (used when the wallpaper path is empty), and each
connected output is stored as:

```conf
monitor.DP-1=on,1920x1080,0,0,normal,yes
```

The fields are enabled (`on`/`off`), resolution (or `auto`), X, Y, rotation
(`normal`, `left`, `right`, `inverted`), and primary (`yes`/`no`). Wallpaper
styles are `fill`, `fit`, `center`, and `tile`. Monitor output names and values
are validated; configuration is parsed as data only.

To restore settings at login, copy
`autostart/gnuchan-desktop-panel.desktop` into
`~/.config/autostart/gnuchan-desktop-panel.desktop`. It runs
`gnuchan-desktop-panel --apply-saved` without opening a window. The desktop entry
can also be launched directly. Config validation without applying:

```sh
gnuchan-desktop-panel --check-config
```

## Version

1.0.0
