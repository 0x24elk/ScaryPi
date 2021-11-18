#!/usr/bin/python

"""Shows animated 'eyes' on two 8x8 LED matrices.

Matrices are driven by a MAX7219 or similar. We interface
with them through the luma.led_matrix library.

For local development without hardware try something like:
./scarypi.py -d pygame --transform=led_matx --width 16 --height 8

For actual deployment with hardware (controlled through GPIO):
./scarypi.py -d max7219 --width 16 --height 8 \
  --interface spi --block-orientation=90
"""

import sys
import datetime
import random
import time

from PIL import Image

from luma.core import cmdline
from luma.core.interface.serial import spi, noop
from luma.core.render import canvas
from luma.core.virtual import viewport

class Point(object):
  """A point, because a tuple is soo yesterday."""
  def __init__(self, x, y):
    self.x = x
    self.y = y

  def __str__(self):
    return "(%s, %s)" % (self.x, self.y)


class Animation(object):
  """Interface for an animation."""

  def __init__(self):
    """Creates a new animation."""
    self.start = None  # The start time, once begun.
    self.done = False

  def begin(self, now):
    """Starts the animation at now milliseconds."""
    self.start = now

  def tick(self, now):
    """Performs a step of the animation based on the current time."""


class LinearAnimation(Animation):
  """Based class for linear animations."""

  def __init__(self, duration_ms):
    """Creates a new animation of length duration_ms milliseconds."""
    Animation.__init__(self)
    self.duration_ms = duration_ms

  def tick(self, now):
    """Performs a step of the animation based on the current time."""
    Animation.tick(self, now)
    dt_timedelta = (now - self.start)
    dt = dt_timedelta.total_seconds() * 1000
    if dt <= 0:
      return  # Bail if we're called too fast or going back in time.
    if dt <= self.duration_ms:
      self._animate(dt / self.duration_ms)
    else:
      self._animate(1.0)
      self.done = True

  def _animate(self, pct):
    """Overwrite in subclasses to performs a step, based on a percentage completion."""    


class AnimationGroup(Animation):
  """Plays a group of Animations in parallel until all are done."""

  def __init__(self, *args):
    """Initializes the animation with a list of animations."""
    Animation.__init__(self)
    self.animations = args
    self.done = False

  def begin(self, now):
    Animation.begin(self, now)
    for a in self.animations:
      a.begin(now)

  def tick(self, now):
    Animation.tick(self, now)
    all_done = True
    for a in self.animations:
      a.tick(now)
      if not a.done:
        all_done = False
    self.done = all_done


class AnimationSequence(Animation):
  """Plays a set of Animations in sequence."""

  def __init__(self, *args):
    Animation.__init__(self)
    self.animations = list(args)
    self.active = None

  def tick(self, now):
    """Advances the head animation in the queue, removing done ones."""
    Animation.tick(self, now)
    # End current animation, if done.
    if self.active and self.active.done:
      self.active = None

    # Pop next animation from queue and start, if none.
    if not self.active:
      if self.animations:
        self.active = self.animations.pop(0)
        self.active.begin(now)
        return

    # No more animations => done.
    if not self.active:
      self.done = True
      return

    self.active.tick(now)


class Look(LinearAnimation):
  """An animation moving the pupil of an Eye."""

  def __init__(self, eye, where, duration_ms=200):
     """Moves the eyeball to a given Point where."""
     LinearAnimation.__init__(self, duration_ms)
     self.eye = eye
     self.origin = eye.pupil
     self.dest = where
     self.dx = self.dest.x - self.origin.x
     self.dy = self.dest.y - self.origin.y
     if self.dx == 0 and self.dy == 0:
       self.done = True

  def _animate(self, pct):
    if self.done:
      return
    curr = Point(int(self.origin.x + (self.dx * pct)),  int(self.origin.y + (self.dy * pct)))
    self.eye._look(curr)


class Blink(LinearAnimation):
  """An animation blinking an Eye."""

  def __init__(self, eye, duration_ms=500):
     """Blinks the eye in duration_ms"""
     LinearAnimation.__init__(self, duration_ms)
     self.eye = eye
     self.eyelid = 0  # Offset of the eyelids, 0=open, 3=closed

  def _animate(self, pct):
    if self.done:
      return
    # Close eyelids 0->4 in first half of animation, then re-open.
    if (pct < 0.5):
      offset = 4 * (pct / 0.49) + 0.5
      self.eye._eyelids(int(offset))
    else:
      offset = 4 - (4 * ((pct - 0.5) / 0.49) + 0.5)
      self.eye._eyelids(int(offset))
    # Ensure eyes fully open again at end of animation.
    if pct >= 1.0:
      self.eye._eyelids(-1)
      return


class CrossEyes(AnimationSequence):
  """Crosses the eyes."""
  def __init__(self, left, right, duration_ms=3000):
    ms = duration_ms / 3
    AnimationSequence.__init__(self,
      AnimationGroup(left.look(Point(6, 4), ms), right.look(Point(2, 4), ms)),
      Wait(ms),
      AnimationGroup(left.look(Point(4, 4), ms), right.look(Point(4, 4), ms))
    )


class MethEyes(AnimationSequence):
  """Inverse 'cross eyes', looking out."""
  def __init__(self, left, right, duration_ms=3000):
    ms = duration_ms / 3
    AnimationSequence.__init__(self,
      AnimationGroup(left.look(Point(2, 4), ms), right.look(Point(6, 4), ms)),
      Wait(ms),
      AnimationGroup(left.look(Point(4, 4), ms), right.look(Point(4, 4), ms))
    )


class CrazyBlink(AnimationSequence):
  """Blinks left eye, then right."""
  def __init__(self, left, right, duration_ms=1500):
    ms = duration_ms / 2
    AnimationSequence.__init__(self,
      left.blink(ms),
      right.blink(ms)
    )


class LazyEye(AnimationSequence):
  """Lowers pupil of a single eye only."""
  def __init__(self, eye, duration_ms=2000):
    ms = duration_ms / 3
    AnimationSequence.__init__(self,
      eye.look(Point(4, 6), ms * 2),  # Lower slowly
      eye.look(Point(4, 4), ms),      # Raise quickly
    )


class CrazySpin(AnimationSequence):
  """'Spins' pupil horizontally with wraparound."""
  def __init__(self, left, right, duration_ms=400):
    times = 2
    ms = duration_ms / (times*8)
    a = []
    # Just keep moving to the left, as the Eye class handles wrapping.
    for i in range(0, times*8):
      x = 4 - i
      a.append(AnimationGroup(left.look(Point(x, 4), ms), right.look(Point(x, 4), ms)))
    AnimationSequence.__init__(self, *a)


class RoundSpin(AnimationSequence):
  """Spins the eyeballs of both eyes in circles."""
  def __init__(self, left, right, duration_ms=400):
    times = 2
    ms = duration_ms / (times*13 + 1)
    a = [AnimationGroup(left.look(Point(6, 4), ms), right.look(Point(2, 4), ms))]
    for i in range(times):
      a = a + [
        AnimationGroup(left.look(Point(6, 4), ms), right.look(Point(2, 4), ms)),
        AnimationGroup(left.look(Point(6, 3), ms), right.look(Point(2, 3), ms)),
        AnimationGroup(left.look(Point(5, 2), ms), right.look(Point(3, 2), ms)),
        AnimationGroup(left.look(Point(4, 2), ms), right.look(Point(4, 2), ms)),
        AnimationGroup(left.look(Point(3, 2), ms), right.look(Point(5, 2), ms)),
        AnimationGroup(left.look(Point(2, 3), ms), right.look(Point(6, 3), ms)),
        AnimationGroup(left.look(Point(2, 4), ms), right.look(Point(6, 4), ms)),
        AnimationGroup(left.look(Point(2, 5), ms), right.look(Point(6, 5), ms)),
        AnimationGroup(left.look(Point(3, 6), ms), right.look(Point(5, 6), ms)),
        AnimationGroup(left.look(Point(4, 6), ms), right.look(Point(4, 6), ms)),
        AnimationGroup(left.look(Point(5, 6), ms), right.look(Point(3, 6), ms)),
        AnimationGroup(left.look(Point(6, 5), ms), right.look(Point(2, 5), ms)),
        AnimationGroup(left.look(Point(6, 4), ms), right.look(Point(2, 4), ms))
      ]
    AnimationSequence.__init__(self, *a)


class GlowEyes(LinearAnimation):
  """Glows the eyes; well, rather the device."""

  def __init__(self, device, duration_ms=300):
     """Blinks the eye in duration_ms"""
     LinearAnimation.__init__(self, duration_ms)
     self.device = device

  def _animate(self, pct):
    if self.done:
      return
    # Increase contrast 30->150 in first half of animation, then bring down again.
    if (pct < 0.5):
      c = int(30 + 120 * (pct / 0.49))
      self.device.contrast(c)
    else:
      c = int(150 - 120 * ((pct - 0.5) / 0.49))
      self.device.contrast(c)
    # Ensure eyes fully open again at end of animation.
    if pct >= 1.0:
      self.device.contrast(30)


class Wait(LinearAnimation):
  """An animation doing nothing."""

  def __init__(self, eye, duration_ms=300):
     """Waits for duration_ms"""
     LinearAnimation.__init__(self, duration_ms)


class Eye(object):
  """A single 8x8 eye we animate and draw on our LED matrix."""

  # Basic eyeball template (without a pupil).
  eye_ball = [
    0b00111100,
    0b01111110,
    0b11111111,
    0b11111111,
    0b11111111,
    0b11111111,
    0b01111110,
    0b00111100
  ]

  def __init__(self):
    """Initializes the eye."""
    self.pixels = bytearray(Eye.eye_ball)
    # The center of the pupil, so 4,4 is looking straight ahead.
    self.pupil = Point(4,4)
    # The offset of the eyelid(s) from the top/bottom. < 0 for fully open.
    self.eyelids = -1

  def _on(self, x, y):
    """Flips the pixel at x,y on. Wraps if x/y out of bounds."""
    y = y % 8
    x = x % 8
    self.pixels[y] = self.pixels[y] | (0b00000001 << (7 - x))

  def _off(self, x, y):
    """Flips the pixel at x,y off. Wraps if x/y out of bounds."""
    y = y % 8
    x = x % 8
    self.pixels[y]  = self.pixels[y] & ~(0b00000001 << (7 - x))

  def _row_on(self, y):
    """Flips the whole row at y on. Wraps if y out of bounds."""
    y = y % len(self.pixels)
    self.pixels[y] = 0b11111111

  def _row_off(self, y):
    """Flips the whole row at y off. Wraps if y out of bounds."""
    y = y % len(self.pixels)
    self.pixels[y] = 0b00000000

  def _look(self, pos):
    """Immediately moves the pupil of the eyeball to pos."""
    self.pupil = pos
    self.pupil.x = self.pupil.x % 8
    self.pupil.y = self.pupil.y % 8

  def _eyelids(self, offset):
    """Moves the eyelids to the given offset, -1=open, 3=closed."""
    self.eyelids = max(-1, min(offset, 3))

  def look(self, pos, duration_ms=300):
    """Returns an animation, moving the puil to pos in duration_ms."""
    return Look(self, pos, duration_ms)

  def blink(self, duration_ms=500):
    """Returns an animation, blinking the eye in duration_ms."""
    return Blink(self, duration_ms)

  def image(self):
    """Renders the current state of the eye into an 8x8 monochrome image."""
    self.pixels = bytearray(Eye.eye_ball)
    # Draw pupil
    self._off(self.pupil.x-1,self.pupil.y-1)
    self._off(self.pupil.x,self.pupil.y-1)
    self._off(self.pupil.x-1,self.pupil.y)
    self._off(self.pupil.x,self.pupil.y)
    # Draw eyelids, if requested.
    if self.eyelids >= 0:
      for i in xrange(0, self.eyelids + 1):
        self._row_off(i)
        self._row_off(7-i)
    return Image.frombytes('1', (8, 8), bytes(self.pixels))


def get_device(actual_args):
  parser = cmdline.create_parser(description='luma.examples arguments')
  args = parser.parse_args(actual_args)
  if args.config:
    # load config from file
    config = cmdline.load_config(args.config)
    args = parser.parse_args(config + actual_args)
  # create device
  device = cmdline.create_device(args)
  return device

# General animation tick
TICK_SECONDS = 0.1

def render(left, right, device):
  """Renders the current state of the eyes on device."""
  with canvas(device) as draw:
    draw.bitmap((0, 0), left.image(), fill="white")
    draw.bitmap((8, 0), right.image(), fill="white")

def pick_effect(device, left, right):
  i = random.randint(0, 6)
  if i == 0:
    return CrossEyes(left, right)
  if i == 1:
    return CrazySpin(left, right)
  if i == 2:
    return MethEyes(left, right)
  if i == 3:
    return CrazyBlink(left, right)
  if i == 4:
      return LazyEye(left)
  if i == 5:
      return RoundSpin(left, right)
  return GlowEyes(device)

def animation_loop(device):
  left = Eye()
  right = Eye()
  main_sequence = AnimationSequence()
  while(True):
    start = datetime.datetime.now()

    # Insert the next round of animations, if queue empty.
    if main_sequence.done:
      animations = []
      # Look to a random point
      p = Point(random.randint(2,5), random.randint(2,5))
      animations.append(
        AnimationGroup(left.look(p), right.look(p)))
      # Wait 2.5 - 3.5s
      animations.append(Wait(random.randint(5,7) * 500))
      # Maybe blink
      if random.randint(0, 3) == 0:
        animations.append(
          AnimationGroup(left.blink(), right.blink()))
      # Play an effect, if desired.
      if random.randint(0, 6) == 0:
        animations.append(pick_effect(device, left, right))
      main_sequence = AnimationSequence(*animations)

    # Animate
    main_sequence.tick(start)

    render(left, right, device)

    # Sleep if we're going too fast.
    elapsed = datetime.datetime.now() - start
    sleeptime = max(TICK_SECONDS - elapsed.total_seconds(), 0)
    time.sleep(sleeptime)


def main():
  device = get_device(sys.argv[1:])
  device.contrast(30)
  animation_loop(device)


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    pass
