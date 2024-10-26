import logging
import threading
from typing import Dict

from cie_xy_to_hsv import cie_xy_to_hsv

logger = logging.getLogger(__name__)

# Map scene light names to actual device names
LIGHT_NAME_MAP = {
    "Ceiling": "John's Ceiling",
    "Bed vertical": "John's Bedside",
}


class LightDevice:
    def __init__(self, hub, light):
        self._hub = hub
        self._light = light
        self._name = light.attributes.custom_name

    def apply_action(self, action: dict) -> None:
        """Process and send an action dict to the light"""

        def send_light_command():
            # Log incoming Hue command
            hue_attrs = {k[4:]: v for k, v in action.items() if k.startswith("Hue_")}
            logger.info(f"t{action.get('Time', 0):.1f}: {self._name}: {hue_attrs}")
            transition = action.get("Hue_transitiontime", 0) * 100

            # First turn on if needed
            if action.get("Hue_on") == True:
                data = {"attributes": {"isOn": True}}

                time = action["Time"]
                logger.info(f"t{time:.1f}: {self._name}: {data}")
                self._send_command(data)

            # Then apply color/brightness settings
            if "Hue_bri" in action:
                level = int(action["Hue_bri"] / 254 * 99 + 1)
                data = {
                    "attributes": {"lightLevel": level},
                    "transitionTime": transition,
                }

                time = action["Time"]
                logger.info(f"t{time:.1f}: {self._name}: {data}")
                self._send_command(data)

            if "Hue_ct" in action:
                kelvin = int(1000000 / action["Hue_ct"])
                data = {
                    "attributes": {"colorTemperature": kelvin},
                    "transitionTime": transition,
                }

                time = action["Time"]
                logger.info(f"t{time:.1f}: {self._name}: {data}")
                self._send_command(data)

            if "Hue_xy" in action:
                x, y = action["Hue_xy"]
                hue, sat, _ = cie_xy_to_hsv(x, y)
                data = {
                    "attributes": {"colorHue": hue * 360, "colorSaturation": sat},
                    "transitionTime": transition,
                }

                time = action["Time"]
                logger.info(f"t{time:.1f}: {self._name}: {data}")
                self._send_command(data)

            # Finally turn off if needed
            if action.get("Hue_on") == False:
                data = {"attributes": {"isOn": False}}

                time = action["Time"]
                logger.info(f"t{time:.1f}: {self._name}: {data}")
                self._send_command(data)

        threading.Thread(target=send_light_command).start()

    def _send_command(self, data: dict):
        """Send command to DIRIGERA hub and log it"""
        try:
            self._hub.patch(route=f"/devices/{self._light.id}", data=[data])
        except Exception as e:
            logger.error(f"Failed to send command to {self._name}: {e}")


class LightController:
    """Registry of available lights with name mapping"""

    def __init__(self, hub, room_name: str):
        lights = [
            lt for lt in hub.get_lights() if lt.room and lt.room.name == room_name
        ]

        if not lights:
            raise RuntimeError(f"No lights found in room: {room_name}")

        self._lights = {
            light.attributes.custom_name: LightDevice(hub, light) for light in lights
        }

    def apply_action(self, light_name: str, action: dict) -> None:
        """Apply a command to the specified light"""
        device_name = LIGHT_NAME_MAP.get(light_name, light_name)
        if light := self._lights.get(device_name):
            light.apply_action(action)
        else:
            logger.warning(f"Light not found: {light_name} -> {device_name}")
