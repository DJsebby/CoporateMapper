"""Offline test for crawler.env. Uses a temp .env file; no network calls."""

import importlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class LoadEnvTests(unittest.TestCase):
    def test_load_env_sets_variables_from_env_file(self):
        with TemporaryDirectory() as tmp:
            fake_repo_root = Path(tmp)
            env_file = fake_repo_root / ".env"
            env_file.write_text("TEST_ONLY_CRAWLER_VAR=hello\n", encoding="utf-8")

            import crawler.env as env_module

            importlib.reload(env_module)
            with patch.object(env_module, "_ENV_PATH", env_file), patch.object(
                env_module, "_loaded", False
            ):
                os.environ.pop("TEST_ONLY_CRAWLER_VAR", None)
                env_module.load_env()
                self.assertEqual(os.environ.get("TEST_ONLY_CRAWLER_VAR"), "hello")
            os.environ.pop("TEST_ONLY_CRAWLER_VAR", None)

    def test_load_env_only_loads_once(self):
        import crawler.env as env_module

        importlib.reload(env_module)
        calls = []
        with patch("dotenv.load_dotenv", side_effect=lambda *a, **k: calls.append(1)):
            env_module.load_env()
            env_module.load_env()
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
