import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "gnuchan_desktop_panel.py"
SPEC = importlib.util.spec_from_file_location("gnuchan_desktop_panel", MODULE_PATH)
panel = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = panel
SPEC.loader.exec_module(panel)


XRANDR = """\
Screen 0: minimum 8 x 8, current 3840 x 1080, maximum 32767 x 32767
DP-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis)
   1920x1080     60.00*+ 59.94
   1280x720      60.00
HDMI-1 connected 1920x1080+1920+0 (left)
   1920x1080     60.00*
   1280x720      60.00
DP-2 disconnected (normal left inverted right x axis y axis)
"""


class ConfigTests(unittest.TestCase):
    def test_round_trip_key_value_settings(self):
        config = """# comment
wallpaper=/home/test/wall paper.png
background_color=#24364A
wallpaper_mode=fill
monitor.DP-1=on,1920x1080,-10,0,left,yes
monitor.HDMI-1=off,1280x720,1920,0,normal,no
"""
        parsed = panel.parse_config(config)
        self.assertEqual(parsed.wallpaper, "/home/test/wall paper.png")
        self.assertEqual(parsed.background_color, "#24364A")
        self.assertEqual(parsed.monitors["DP-1"].x, -10)
        self.assertFalse(parsed.monitors["HDMI-1"].enabled)
        restored = panel.parse_config(panel.serialize_config(parsed))
        self.assertEqual(restored.wallpaper_mode, "fill")
        self.assertEqual(restored.background_color, "#24364A")

    def test_rejects_bad_or_executable_config(self):
        literal = panel.parse_config("wallpaper=picture.png; echo not-executed\n")
        self.assertEqual(literal.wallpaper, "picture.png; echo not-executed")
        for bad in (
            "wallpaper_mode=stretch\n",
            "background_color=red\n",
            "monitor.DP-1=on,1920x1080,0,0,normal\n",
            "unknown=yes\n",
            "wallpaper=x\nwallpaper=y\n",
        ):
            with self.subTest(bad=bad), self.assertRaises(panel.PanelError):
                panel.parse_config(bad)

    def test_xrandr_discovery_extracts_layout_modes_and_rotation(self):
        monitors = panel.parse_xrandr_output(XRANDR)
        self.assertEqual([m.name for m in monitors], ["DP-1", "HDMI-1"])
        self.assertEqual(monitors[0].modes, ["1920x1080", "1280x720"])
        self.assertTrue(monitors[0].primary)
        self.assertEqual((monitors[1].x, monitors[1].y, monitors[1].rotation), (1920, 0, "left"))

    def test_apply_builds_argument_vector_and_checks_primary(self):
        monitors = panel.parse_xrandr_output(XRANDR)
        settings = panel.Settings(monitors={m.name: m for m in monitors})
        command = panel.build_xrandr_command(monitors)
        self.assertIn("--pos", command)
        self.assertIn("1920x0", command)
        monitors[0].mode = "auto"
        self.assertIn("--auto", panel.build_xrandr_command(monitors))
        monitors[0].mode = "1920x1080"
        with patch.object(panel, "run_command") as run:
            panel.apply_settings(settings, monitors)
            self.assertEqual(run.call_args.args[0][0], "xrandr")
        monitors[0].primary = False
        with self.assertRaisesRegex(panel.PanelError, "exactly one"):
            panel.apply_settings(settings, monitors)

    def test_settings_are_saved_as_conf_key_value(self):
        settings = panel.Settings()
        with self.subTest():
            self.assertIn("wallpaper_mode=fill", panel.serialize_config(settings))
            self.assertNotIn("import ", panel.serialize_config(settings))

    def test_solid_background_uses_xsetroot_without_a_shell(self):
        monitors = panel.parse_xrandr_output(XRANDR)
        settings = panel.Settings(
            background_color="#123ABC",
            monitors={m.name: m for m in monitors},
        )
        with patch.object(panel.shutil, "which", return_value="/usr/bin/xsetroot"), \
                patch.object(panel, "run_command") as run:
            panel.apply_settings(settings, monitors)
        self.assertEqual(run.call_args_list[1].args[0], ["xsetroot", "-solid", "#123ABC"])


if __name__ == "__main__":
    unittest.main()
