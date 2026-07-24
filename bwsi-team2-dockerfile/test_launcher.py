"""Focused tests for the Docker/SSH launcher.

These tests mock Docker and SSH so they are safe to run without a daemon.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import call, patch


LAUNCHER_PATH = Path(__file__).with_name("launcher.py")
SPEC = importlib.util.spec_from_file_location("maze_launcher_under_test", LAUNCHER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {LAUNCHER_PATH}")
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        launcher._ACTIVE_LEVEL = launcher.DEFAULT_LEVEL
        launcher._IMAGE_READY = False

    def test_each_level_gets_its_own_port(self):
        with patch.object(launcher, "BASE_HOST_PORT", 2222):
            self.assertEqual(launcher.port_for(1), 2222)
            self.assertEqual(launcher.port_for(5), 2226)
            with self.assertRaises(ValueError):
                launcher.port_for(0)

    def test_start_container_binds_only_to_loopback(self):
        with (
            patch.object(launcher.subprocess, "run") as remove,
            patch.object(launcher, "run", return_value=0) as run,
        ):
            self.assertEqual(launcher.start_container(3), 0)

        remove.assert_called_once_with(
            ["docker", "rm", "-f", "maze-level3"],
            capture_output=True,
        )
        run.assert_called_once_with(
            [
                "docker",
                "run",
                "-d",
                "--name",
                "maze-level3",
                "-p",
                "127.0.0.1:2224:22",
                launcher.IMAGE_NAME,
            ]
        )
        self.assertEqual(launcher._ACTIVE_LEVEL, 3)

    def test_default_readiness_check_uses_most_recent_level(self):
        launcher._ACTIVE_LEVEL = 4
        fake_socket = unittest.mock.MagicMock()
        fake_socket.__enter__.return_value = fake_socket
        fake_socket.recv.return_value = b"SSH-2.0-OpenSSH_8.9\r\n"

        with (
            patch("socket.socket", return_value=fake_socket),
            patch.object(launcher.time, "time", side_effect=[0, 0]),
        ):
            self.assertTrue(launcher.wait_for_ssh(timeout_seconds=1))

        fake_socket.connect.assert_called_once_with(
            (launcher.DEFAULT_HOST, launcher.port_for(4))
        )

    def test_build_refreshes_once_then_uses_process_cache(self):
        with patch.object(launcher, "run", return_value=0) as run:
            self.assertEqual(launcher.build_image(1), 0)
            self.assertEqual(launcher.build_image(2), 0)

        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][0:2], ["docker", "build"])

    def test_transient_ssh_failure_retries_without_new_session(self):
        with (
            patch.object(launcher, "SSH_ATTEMPTS", 3),
            patch.object(launcher, "wait_for_ssh", return_value=True),
            patch.object(launcher, "run", side_effect=[255, 0]) as run,
            patch.object(launcher.time, "sleep"),
            patch.object(launcher.sys.stdin, "isatty", return_value=False),
        ):
            self.assertEqual(launcher.launch_ssh_in_place(2), 0)

        expected_command = [
            str(launcher.CONNECT_SCRIPT),
            "2",
            launcher.DEFAULT_HOST,
            "2223",
        ]
        self.assertEqual(
            run.call_args_list,
            [call(expected_command), call(expected_command)],
        )

    def test_normal_ssh_exit_is_not_retried(self):
        with (
            patch.object(launcher, "wait_for_ssh", return_value=True),
            patch.object(launcher, "run", return_value=0) as run,
            patch.object(launcher.sys.stdin, "isatty", return_value=False),
        ):
            self.assertEqual(launcher.launch_ssh_in_place(1), 0)

        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
