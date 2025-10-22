import types
import unittest

from main import Game, MODE_MAZE, MODE_TOWN, MODE_SCENE


class ThreatResetTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.__new__(Game)
        # Minimal attributes required by on_mode_changed
        self.game.mode = MODE_MAZE
        self.game.threat = 60
        self.game.threat_max = 100
        self.game.threat_full_steps = 5
        self.game.threat_flash_active = True
        self.game.threat_flash_t0 = 42
        self.game.scene_active = False
        self.game.scene_from = MODE_MAZE
        self.game.scene_to = MODE_TOWN
        self.game.scene_stage = 0
        self.game.scene_t0 = 0
        self.game.scene_dur = (0, 0, 0)
        self.game.music = types.SimpleNamespace(enabled=False)

        def start_scene_transition(from_mode, to_mode, *_args):
            self.game.scene_from = from_mode
            self.game.scene_to = to_mode
            self.game.mode = MODE_SCENE

        self.game.start_scene_transition = start_scene_transition

    def test_threat_resets_when_returning_to_town(self):
        # simulate mode change detection loop
        Game.on_mode_changed(self.game, MODE_MAZE, MODE_TOWN)

        self.assertEqual(self.game.threat, 0)
        self.assertEqual(self.game.threat_full_steps, 0)
        self.assertFalse(self.game.threat_flash_active)
        self.assertEqual(self.game.scene_to, MODE_TOWN)


if __name__ == "__main__":
    unittest.main()
