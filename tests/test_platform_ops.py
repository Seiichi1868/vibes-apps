import unittest
import tempfile
import os

from platform_ops.registry import PLATFORM_APPS
from platform_ops.runtime import (
    is_path_operational,
    list_apps_with_status,
    set_app_operational,
)


class PlatformOpsTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._prev = os.environ.get("PLATFORM_OPS_DATA_DIR")
        os.environ["PLATFORM_OPS_DATA_DIR"] = self._tmpdir.name

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("PLATFORM_OPS_DATA_DIR", None)
        else:
            os.environ["PLATFORM_OPS_DATA_DIR"] = self._prev
        self._tmpdir.cleanup()

    def test_default_all_operational(self):
        self.assertTrue(is_path_operational("/news/lesson"))
        self.assertTrue(is_path_operational("/toolbox/timer"))

    def test_maintenance_blocks_app_paths(self):
        set_app_operational("news", False)
        self.assertFalse(is_path_operational("/news/"))
        self.assertFalse(is_path_operational("/news/api/youtube-transcript"))
        self.assertTrue(is_path_operational("/toolbox/admin"))

    def test_toolbox_admin_bypass_when_toolbox_off(self):
        set_app_operational("toolbox", False)
        self.assertFalse(is_path_operational("/toolbox/timer"))
        self.assertTrue(is_path_operational("/toolbox/admin"))
        self.assertTrue(is_path_operational("/toolbox/admin/api/settings"))

    def test_vibespeak_root_only(self):
        set_app_operational("vibespeak", False)
        self.assertFalse(is_path_operational("/"))
        self.assertFalse(is_path_operational("/admin"))
        self.assertTrue(is_path_operational("/toolbox"))

    def test_list_apps_matches_registry(self):
        rows = list_apps_with_status()
        self.assertEqual(len(rows), len(PLATFORM_APPS))


if __name__ == "__main__":
    unittest.main()
