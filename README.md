# ScaryPi
Animated Halloween Pumpkin Eyes - Raspberry Pi Style

![Assembled Pumpkin](pumpkin.png)

*Note: unless you have a spare Raspberry Pi lying around, I recommend
building this project with an [Arduino](https://github.com/0x24elk/ScaryDuino)
instead. The Arduino is cheaper, "boots" faster and will need less power.
But then, when I originally started this project, I did have a spare
Raspberry Pi. So there you go.*

## Parts (aka BOM)

  * Raspberry Pi (e.g., a Raspberry Pi 2 Model B)
  * 2x MAX7219 8x8 LED Modules
  * Wires
  * Pumpkin (or sth else you would like to look at you and wink ;)

## Assembly

Solder up your LED modules, if required. Connect the modules in a
daisy-chained configuration to the Raspberry Pi's GPIO pins as
described [here](https://www.hackster.io/bkkirankumar2/max7219-interfacing-with-raspberry-pi-2-windows-10-b8ed17),
based on the [RPi 2 Pinout](https://pi4j.com/1.2/pins/model-2b-rev1.html)

|  Raspberry Pi    |LED Array|
|------------------|---------|
|  Pin  2: 5V      |   VCC   |
|  Pin  6: GND     |   GND   |
|  Pin 19: MOSI    |   DIN   |
|  Pin 23: SCLK    |   CLK   |
|  Pin 24: CE0     |   CS    |

## Setup

Next, prepare the Raspberry Pi.

### Enabling SPI

Enable the SPI interface via RaspiConfig.

    $ sudo raspi-config
      # Choose <Advanced Settings>
      # Choose <Enable SPI>
    $ sudo reboot

Grant the user you plan to run the code under access to the devices.

    $ sudo usermod -a -G spi,gpio <user>
    # Log in again

### Installing libraries

Install the [LumaLED](https://luma-led-matrix.readthedocs.io/en/latest/) library.

    $ sudo apt install build-essential python-dev python-pip libfreetype6-dev libjpeg-dev libopenjp2-7 libtiff5
    $ sudo -H pip install --upgrade --ignore-installed pip setuptools
    $ sudo -H pip install --upgrade luma.led_matrix

If you like, verify you have your displays connected correctly by running some example code:

    $ wget https://raw.githubusercontent.com/rm-hull/luma.led_matrix/master/examples/matrix_demo.py
    $  python matrix_demo.py --cascaded 2

### Running the code

With SPI/GPIO set up and the libraries installed you should be able to run `scarypi.py`.

    $ ./scarypi.py -d max7219 --width 16 --height 8 --interface spi --block-orientation=90

This should now display the animated eyes on the matrices.

### Start at boot

If you want to automatically start the animation script at boot you can use a systemd service.
You can use `scarypi.service` as a starting point (you'll need to update that with the right
path, and if you don't want to run as root, add some user)

    $ sudo cp scarypi.service /lib/systemd/system
    $ sudo chmod 644 /lib/systemd/system/scarypi.service
    $ sudo systemctl daemon-reload
    $ sudo systemctl enable scarypi.service

## Code

The code is a python rewrite of this [Arduino code](https://github.com/michaltj/LedEyes).

I wasn't sure how much I'd have to worry about random delays from other system processes,
etc. So I decided to go for a time-based animation where we'd skip animation frames if the
code experienced delays. Most of the code centers around the idea of the `LinearAnimation`
class that abstracts away the timekeeping and allows drawing an animation
linear-interpolation style. The `_animate` method gets invoked with a (misnamed) `pct`
parameter in range `[0, 1.0]` telling what state of the animation we want to draw
(0 is the start, 1.0 is the done animation).

Animations can then be combined using the `AnimationGroup` and `AnimationSequence` classes.
`AnimationGroup` plays multiple animations in parallel (e.g., when blinking both eyes at the
same time). And `AnimationSequence` plays them after one another. These can be nested
to produce complex animations.

The main loop of the program then simply becomes assembling a sequence of animations
(including some no-op `Wait` animations, where needed) and invoking their `tick` method
at a regular cadence until they are done. Rinse, repeat, blink, blink.

## Acknoledgements

This is my version of [Michal T Janyst's project](https://mjanyst.weebly.com/arduino-pumpkin-eyes.html). 
I loved the idea and wanted to build my own for some Halloween fun, but decided to do this
with a RaspberryPi and python instead of and Arduino.

I've since also created another [Arduino version](https://github.com/0x24elk/ScaryDuino).
