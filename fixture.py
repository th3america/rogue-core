"""Evaluator-owned synthetic world. Its source and hidden rule are not sent to Rogue."""
import copy


class TinyWorld:
    def __init__(self, special=3, width=7, variant='local-reversal'):
        self.x = 0; self.special = special; self.width = width; self.variant = variant
        self.cells = [0] * width; self.cells[special] = 7

    def observe(self):
        return {'cells': copy.deepcopy(self.cells), 'x': self.x, 'goal': self.width-1,
                'terminal': self.x == self.width-1}

    def act(self, dx):
        if type(dx) is not int or dx not in (-1, 1): raise ValueError('Invalid action')
        effect = -dx if self.variant == 'local-reversal' and self.x == self.special else dx
        dest = self.x + effect
        if 0 <= dest < self.width: self.x = dest
        return self.observe()

    def checkpoint(self):
        return {'x': self.x, 'special': self.special, 'width': self.width, 'variant': self.variant}

    @classmethod
    def restore(cls, value):
        world = cls(value['special'], value['width'], value['variant']); world.x = value['x']; return world

