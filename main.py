from scenefile import SceneFile, scenefile_named

import dirigera  # https://github.com/Leggin/dirigera
from dotenv import load_dotenv

import logging
import os
import sched
import subprocess
import sys


load_dotenv()  # take environment variables from .env.

DIRIGERA_TOKEN = os.getenv("DIRIGERA_TOKEN")
DIRIGERA_IP_ADDRESS = os.getenv("DIRIGERA_IP_ADDRESS")
ROOM_NAME = os.getenv("ROOM_NAME", "Bedroom")

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel("INFO")


def xy_to_hsv(x, y, brightness=1.0):
    """
    Convert CIE xy coordinates to HSV color space.

    Args:
        x (float): x coordinate in CIE color space (0.0 to 1.0)
        y (float): y coordinate in CIE color space (0.0 to 1.0)
        brightness (float): brightness value (0.0 to 1.0)

    Returns:
        tuple: (hue, saturation, value) where:
            hue is 0-360
            saturation is 0.0-1.0
            value is 0.0-1.0
    """
    # Input validation
    if not (0 <= x <= 1 and 0 <= y <= 1):
        raise ValueError("x and y must be between 0 and 1")
    if not (0 <= brightness <= 1):
        raise ValueError("brightness must be between 0 and 1")

    # Calculate z from x and y
    z = 1.0 - x - y

    # Calculate XYZ values
    Y = brightness
    X = (Y / y) * x
    Z = (Y / y) * z

    # XYZ to RGB conversion matrix
    r = X * 3.2406 + Y * -1.5372 + Z * -0.4986
    g = X * -0.9689 + Y * 1.8758 + Z * 0.0415
    b = X * 0.0557 + Y * -0.2040 + Z * 1.0570

    # Apply gamma correction and normalize RGB values
    r = max(0, min(1, r))
    g = max(0, min(1, g))
    b = max(0, min(1, b))

    # Convert RGB to HSV
    maxc = max(r, g, b)
    minc = min(r, g, b)
    v = maxc

    if minc == maxc:
        return 0.0, 0.0, v

    s = (maxc - minc) / maxc
    rc = (maxc - r) / (maxc - minc)
    gc = (maxc - g) / (maxc - minc)
    bc = (maxc - b) / (maxc - minc)

    if r == maxc:
        h = bc - gc
    elif g == maxc:
        h = 2.0 + rc - bc
    else:
        h = 4.0 + gc - rc

    h = (h / 6.0) % 1.0
    h *= 360  # Convert to degrees

    return h, s, v


class ScenePlayer:
    def __init__(self, dirigera_hub):
        assert dirigera_hub

        self._hub = dirigera_hub

        lights = dirigera_hub.get_lights()
        self._lights = [lt for lt in lights if lt.room and lt.room.name == ROOM_NAME]
        if len(self._lights) == 0:
            sys.exit("Room not found")

        self._scheduler = sched.scheduler()
        self._audioproc = None

    def _load_schedule_from_scenefile(self, scenefile):
        logger.debug("_load_schedule_from_scenefile({})".format(scenefile.scene_id))

        def _perform_action(action_dict):
            logger.debug("t{:.3f}: {}".format(action_dict["Time"], action_dict))

            if action_dict["Type"] == "Audio":
                path = action_dict["File"]
                self._audioproc = subprocess.Popen(["afplay", path])

                logger.info(self._audioproc)
            elif action_dict.get("LightName"):
                light_name = action_dict["LightName"]

                hue_effect_dict = {
                    k.replace("Hue_", ""): v
                    for k, v in action_dict.items()
                    if k.startswith("Hue_")
                }

                dirigera_dict = {"attributes": {}}

                # https://github.com/jsiegenthaler/hueget#on-get-and-set
                value = hue_effect_dict.get("on")
                if value != None:
                    dirigera_dict["attributes"]["isOn"] = value

                # https://github.com/jsiegenthaler/hueget#bri-get-and-set
                value = hue_effect_dict.get("bri")
                if value != None:
                    dirigera_dict["attributes"]["lightLevel"] = int(
                        value / 254 * 99 + 1
                    )

                # https://github.com/jsiegenthaler/hueget#ct-get-and-set
                value = hue_effect_dict.get("ct")
                if value != None:
                    dirigera_dict["attributes"]["colorTemperature"] = int(
                        1000000 / value
                    )

                # https://github.com/jsiegenthaler/hueget#xy-get-and-set
                value = hue_effect_dict.get("xy")
                if value != None:
                    x, y = value
                    hue, saturation, value = xy_to_hsv(x, y)
                    dirigera_dict["attributes"]["colorHue"] = int(hue)
                    dirigera_dict["attributes"]["colorSaturation"] = int(saturation)
                    dirigera_dict["attributes"]["lightLevel"] = int(value * 99 + 1)

                value = hue_effect_dict.get("transitiontime")
                if value != None:
                    transitiontime = value * 100
                    dirigera_dict["transitionTime"] = transitiontime

                for light in self._lights:
                    try:
                        if (
                            light_name == "Ceiling"
                            and light.attributes.custom_name == "Ceiling Lamp"
                        ) or (
                            light_name == "Bed vertical"
                            and light.attributes.custom_name == "John's Bedside"
                        ):
                            logger.info(
                                "t{:.1f}: {}: {}".format(
                                    action_dict["Time"],
                                    light_name,
                                    str(hue_effect_dict),
                                )
                            )

                            # print(dirigera_dict)
                            self._hub.patch(
                                route=f"/devices/{light.id}", data=[dirigera_dict]
                            )
                    except Exception as e:
                        logger.error(e)
            else:
                logger.warning("Not implemented:", action_dict)

        for action_dict in scenefile.timeline:
            logger.debug(action_dict)

            self._scheduler.enter(
                action_dict["Time"], 1, _perform_action, argument=(action_dict,)
            )

        # Add empty event so that run() blocks until the full TimeDuration
        self._scheduler.enter(scenefile.info["TimeDuration"], 1, lambda: None)

    def run(self, scenefile=None, path=None, scene_id=None):
        logger.debug("run()")

        if scene_id:
            scenefile = scenefile_named(scene_id)
        elif path:
            scenefile = SceneFile(path)

        assert scenefile
        logger.debug("run({})".format(path))

        self.stop()

        self._load_schedule_from_scenefile(scenefile)
        self._scheduler.run()

    # def start(self):
    #     logger.debug("start()")

    def stop(self):
        logger.debug("stop()")

        for e in self._scheduler.queue:
            self._scheduler.cancel(e)

        if self._audioproc:
            self._audioproc.kill()

    def reset(self):
        logger.debug("reset()")

        self.stop()

        # Turn off all the lights
        for light in self._lights:
            light.set_light(lamp_on=False)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: sceneplayer.py PATH")
    path = sys.argv[1]

    if not DIRIGERA_TOKEN:
        sys.exit("DIRIGERA_TOKEN env var must be set")
    if not DIRIGERA_IP_ADDRESS:
        sys.exit("DIRIGERA_IP_ADDRESS env var must be set")

    try:
        dirigera_hub = dirigera.Hub(
            token=DIRIGERA_TOKEN, ip_address=DIRIGERA_IP_ADDRESS
        )

        player = ScenePlayer(dirigera_hub)
        player.reset()

        player.run(path=path)
    except KeyboardInterrupt:
        player.reset()
