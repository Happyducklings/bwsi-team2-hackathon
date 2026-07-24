"""Regression tests for the level-completion password gate."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


GAME_PATH = Path(__file__).with_name("game v2.py")
SPEC = importlib.util.spec_from_file_location("maze_game_under_test", GAME_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {GAME_PATH}")
game = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(game)


def ready_launcher():
    launcher = MagicMock()
    launcher.build_image.return_value = 0
    launcher.start_container.return_value = 0
    launcher.wait_for_ssh.return_value = True
    launcher.launch_ssh_in_place.return_value = 0
    return launcher


class DoorChallengeTests(unittest.TestCase):
    def run_challenge(self, launcher, password_effect):
        output = io.StringIO()
        with (
            patch.object(game, "_load_launcher", return_value=launcher),
            patch.object(game, "_read_door_password", side_effect=password_effect),
            patch.object(game, "clear_screen"),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            result = game.run_door_challenge(1, None)
        return result, output.getvalue()

    def test_correct_password_is_the_only_success_result(self):
        launcher = ready_launcher()
        result, _ = self.run_challenge(
            launcher,
            [game.LEVEL_PASSWORDS[1]],
        )
        self.assertIs(result, True)

    def test_only_literal_true_can_complete_a_level(self):
        self.assertTrue(game._challenge_allows_level_completion(True))
        for bypass_value in (False, None, "complete", 1, object()):
            with self.subTest(value=bypass_value):
                self.assertFalse(
                    game._challenge_allows_level_completion(bypass_value)
                )

    def test_wrong_password_reconnects_instead_of_unlocking(self):
        launcher = ready_launcher()
        result, _ = self.run_challenge(
            launcher,
            ["wrong", game.LEVEL_PASSWORDS[1]],
        )
        self.assertIs(result, True)
        self.assertEqual(launcher.launch_ssh_in_place.call_count, 2)

    def test_control_c_at_password_prompt_stays_locked(self):
        result, output = self.run_challenge(
            ready_launcher(),
            KeyboardInterrupt(),
        )
        self.assertIs(result, False)
        self.assertIn("remains locked", output)

    def test_eof_at_password_prompt_stays_locked(self):
        result, output = self.run_challenge(
            ready_launcher(),
            EOFError(),
        )
        self.assertIs(result, False)
        self.assertIn("remains locked", output)

    def test_control_c_during_ssh_stays_locked(self):
        launcher = ready_launcher()
        launcher.launch_ssh_in_place.side_effect = KeyboardInterrupt()
        result, output = self.run_challenge(launcher, [])
        self.assertIs(result, False)
        self.assertIn("remains locked", output)

    def test_ssh_status_255_still_shows_password_prompt(self):
        launcher = ready_launcher()
        launcher.launch_ssh_in_place.return_value = 255
        result, _ = self.run_challenge(
            launcher,
            [game.LEVEL_PASSWORDS[1]],
        )
        self.assertIs(result, True)

    def test_signal_terminated_ssh_stays_locked(self):
        launcher = ready_launcher()
        launcher.launch_ssh_in_place.return_value = -15
        result, output = self.run_challenge(launcher, [])
        self.assertIs(result, False)
        self.assertIn("remains locked", output)

    def test_nonzero_remote_logout_still_shows_password_prompt(self):
        launcher = ready_launcher()
        # An interactive shell returns the last remote command's status when
        # the player types `exit`; this is still a successful SSH session.
        launcher.launch_ssh_in_place.return_value = 1
        result, _ = self.run_challenge(
            launcher,
            [game.LEVEL_PASSWORDS[1]],
        )
        self.assertIs(result, True)

    def test_missing_launcher_stays_locked(self):
        output = io.StringIO()
        with (
            patch.object(game, "_load_launcher", side_effect=ImportError("missing")),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            result = game.run_door_challenge(1, None)
        self.assertIs(result, False)
        self.assertIn("remains locked", output.getvalue())


if __name__ == "__main__":
    unittest.main()
