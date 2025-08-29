import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import pygame


def main():
    import importlib.util
    spec = importlib.util.spec_from_file_location('game', 'main.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    pygame.display.init()

    g = mod.Game()
    assert g.mode == mod.MODE_TITLE, f"start mode: {g.mode}"

    # Select New Game
    g.title_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert g.mode == mod.MODE_TOWN, f"after New Game: {g.mode}"

    # Move to last option (Exit to Title) and activate
    for _ in range(8):
        g.town_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    g.town_input(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    assert g.mode == mod.MODE_TITLE, f"after Exit to Title: {g.mode}"
    print('OK: Town Exit to Title works')


if __name__ == '__main__':
    main()

