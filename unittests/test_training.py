import os
import types
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from main import Game, Party, Character, MODE_TRAINING


class DummyLog:
    def __init__(self):
        self.messages = []

    def add(self, message):
        self.messages.append(message)


class TrainingMPGainTests(unittest.TestCase):
    def setUp(self):
        self.game = Game.__new__(Game)
        self.game.party = Party()
        self.game.training_index = 0
        self.game.mode = MODE_TRAINING
        self.game.log = DummyLog()
        self.game.start_trait_selection = lambda *args, **kwargs: None

        hero = Character("Hero", "Fighter")
        hero.exp = 120
        hero.max_mp = 0
        hero.mp = 0
        hero.level = 1
        self.game.party.members.append(hero)

    def test_training_level_up_grants_minimum_mp(self):
        member = self.game.party.members[0]
        prev_max_mp = member.max_mp

        event = types.SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_RETURN)

        Game.training_input(self.game, event)

        self.assertEqual(member.level, 2)
        self.assertEqual(member.exp, 20)
        assert member.max_mp > 0
        mp_diff = member.max_mp - prev_max_mp
        self.assertEqual(member.mp, member.max_mp)
        self.assertIn(f"+{mp_diff} MP", self.game.log.messages[-1])


if __name__ == "__main__":
    unittest.main()
