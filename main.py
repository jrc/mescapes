import http.server
import json
import logging
import os
import sched
import socket
import socketserver
import subprocess
import sys
import threading
import urllib.parse

import dirigera  # https://github.com/Leggin/dirigera
import soco  # https://github.com/SoCo/SoCo
from dotenv import load_dotenv

from cie_xy_to_hsv import cie_xy_to_hsv
from scenefile import SceneFile, scenefile_named

load_dotenv()  # take environment variables from .env.

DIRIGERA_IP_ADDRESS = os.getenv("DIRIGERA_IP_ADDRESS")
DIRIGERA_TOKEN = os.getenv("DIRIGERA_TOKEN")
DIRIGERA_ROOM_NAME = os.getenv("DIRIGERA_ROOM_NAME", "Bedroom")
SONOS_IP_ADDRESS = os.getenv("SONOS_IP_ADDRESS")
SONOS_PLAYER_NAME = os.getenv("SONOS_PLAYER_NAME", "Bedroom")
SONOS_VOLUME = os.getenv("SONOS_VOLUME", 25)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(LOG_LEVEL)


class TCPServerReuse(socketserver.TCPServer):
    def __init__(self, server_address, RequestHandlerClass):
        # Set socket options for address reuse before binding
        self.allow_reuse_address = True
        super().__init__(server_address, RequestHandlerClass)


class AudioServer(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        logger.debug(f"HEAD {self.path}")
        file_path = os.path.join("assets", urllib.parse.unquote(self.path)[1:])
        if os.path.isfile(file_path):
            self.send_response(200)
            self.send_header("Content-type", "audio/mpeg")
            file_size = os.path.getsize(file_path)
            self.send_header("Content-Length", str(file_size))
            self.end_headers()
        else:
            self.send_error(404, "File Not Found")

    def do_GET(self):
        logger.debug(f"GET {self.path}")
        file_path = os.path.join("assets", urllib.parse.unquote(self.path)[1:])
        if os.path.isfile(file_path):
            self.send_response(200)
            self.send_header("Content-type", "audio/mpeg")
            self.end_headers()
            with open(file_path, "rb") as f:
                try:
                    self.wfile.write(f.read())
                except (BrokenPipeError, ConnectionResetError):
                    logger.debug("Client closed connection")
        else:
            self.send_error(404, "File Not Found")


def get_host_ip_address():
    """Return the local ip-address"""
    # Rather hackish way to get the local ip-address, recipy from
    # https://stackoverflow.com/a/166589
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip_address = s.getsockname()[0]
    s.close()
    return ip_address


class ScenePlayer:
    def __init__(self, dirigera_hub, sonos_soco):
        assert dirigera_hub

        self._hub = dirigera_hub

        lights = dirigera_hub.get_lights()
        self._lights = [
            lt for lt in lights if lt.room and lt.room.name == DIRIGERA_ROOM_NAME
        ]
        if len(self._lights) == 0:
            sys.exit("Room not found")

        self._scheduler = sched.scheduler()

        self._http_server = None
        self._sonos_soco = sonos_soco
        self._audioproc = None

    def start_server(self, port=8000):
        self._http_ip_address = get_host_ip_address()
        self._http_port = port
        self._http_server = TCPServerReuse(("", port), AudioServer)
        server_thread = threading.Thread(
            target=self._http_server.serve_forever, daemon=True
        )
        server_thread.start()
        logger.info(f"Server started on port {port}")

    def stop_server(self):
        if self._http_server:
            self._http_server.shutdown()
            self._http_server.server_close()
            self._http_server = None
            logger.info("Server stopped")

    def _load_schedule_from_scenefile(self, scenefile):
        logger.debug("_load_schedule_from_scenefile({})".format(scenefile.scene_id))

        def _apply_light_data_sync(light, action_dict, data):
            logger.info(
                "t{:.1f}: {}: {} => {}".format(
                    action_dict["Time"],
                    light.attributes.custom_name,
                    str(
                        {
                            k[len("Hue_") :]: v
                            for k, v in action_dict.items()
                            if k.startswith("Hue_")
                        }
                    ),
                    json.dumps(data),
                )
            )

            try:
                self._hub.patch(route=f"/devices/{light.id}", data=[data])
            except Exception as e:
                logger.error(e)

        def _apply_light_data(light, action_dict, data):
            t = threading.Thread(
                target=_apply_light_data_sync,
                args=[light, action_dict, data],
            )
            t.start()

        def _apply_audio_data_sync(soco, action_dict, audio_url, volume):
            logger.info(
                "t{:.3f}: Playing {} at volume {}".format(
                    action_dict["Time"], audio_url, volume
                )
            )
            soco.volume = volume
            soco.play_uri(audio_url)

        def _perform_action(action_dict):
            logger.debug("t{:.3f}: {}".format(action_dict["Time"], action_dict))

            if action_dict["Type"] == "Audio":
                path = action_dict["File"]
                if self._sonos_soco:
                    if path.startswith("./assets/"):
                        path = path[len("./assets/") :]
                    path = urllib.parse.quote(path)
                    audio_url = (
                        f"http://{self._http_ip_address}:{self._http_port}/{path}"
                    )

                    _apply_audio_data_sync(
                        self._sonos_soco, action_dict, audio_url, SONOS_VOLUME
                    )
                else:
                    self._audioproc = subprocess.Popen(["afplay", path])
                    logger.info(self._audioproc)
            elif action_dict.get("LightName"):
                light_name = action_dict["LightName"]

                # Convert hotel names to home use
                if light_name == "Ceiling":
                    light_name = "John's Ceiling"
                elif light_name == "Bed vertical":
                    light_name = "John's Bedside"

                for light in self._lights:
                    if light_name == light.attributes.custom_name:
                        # Convert Hue effects to DIRIGERA data

                        # https://github.com/jsiegenthaler/hueget#on-get-and-set
                        on = action_dict.get("Hue_on")
                        if on != None and on == True:
                            value = on
                            data = {"attributes": {"isOn": value}}
                            _apply_light_data(light, action_dict, data)

                        transitionTime = 0
                        value = action_dict.get("Hue_transitiontime")
                        if value != None:
                            transitionTime = value * 100

                        # https://github.com/jsiegenthaler/hueget#bri-get-and-set
                        bri = action_dict.get("Hue_bri")  # 1-254
                        if bri != None:
                            value = int(bri / 254 * 99 + 1)  # 1-100
                            data = {
                                "attributes": {"lightLevel": value},
                                "transitionTime": transitionTime,
                            }
                            _apply_light_data(light, action_dict, data)

                        # https://github.com/jsiegenthaler/hueget#ct-get-and-set
                        ct = action_dict.get("Hue_ct")  # 153-500 (mired)
                        if ct != None:
                            value = int(1000000 / ct)  # 2000-6500 (K)
                            data = {
                                "attributes": {"colorTemperature": value},
                                "transitionTime": transitionTime,
                            }
                            _apply_light_data(light, action_dict, data)

                        # https://github.com/jsiegenthaler/hueget#xy-get-and-set
                        xy = action_dict.get("Hue_xy")  # CIE 1931
                        if xy != None:
                            if action_dict.get("Hue_bri"):
                                logger.warning(
                                    "Scene sets both Hue_bri and Hue_xy; ignoring V from converted HSV"
                                )

                            x, y = xy
                            # brightness = bri / 254 if bri else 1
                            hue, saturation, value = cie_xy_to_hsv(x, y)

                            # data = {
                            #     "attributes": {
                            #         "lightLevel": int(value * 99 + 1),
                            #     },
                            #     "transitionTime": transitionTime,
                            # }
                            # _apply_light_data(light, action_dict, data)

                            colorHue = hue * 360  # 0.0-360.0
                            colorSaturation = saturation  # 0.0-1.0
                            data = {
                                "attributes": {
                                    "colorHue": colorHue,
                                    "colorSaturation": colorSaturation,
                                },
                                "transitionTime": transitionTime,
                            }
                            _apply_light_data(light, action_dict, data)

                        # DIRIGERA doesn't allow setting multiple attributes at once
                        # so if turning off a light (like at the start of a scene)
                        # do it last, so the other attributes will take effect first
                        # https://github.com/jsiegenthaler/hueget#on-get-and-set
                        on = action_dict.get("Hue_on")
                        if on != None and on == False:
                            value = on
                            data = {"attributes": {"isOn": value}}
                            _apply_light_data(light, action_dict, data)
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

        self.start_server()  # Start server before scene playback
        try:
            self._load_schedule_from_scenefile(scenefile)
            self._scheduler.run()
        finally:
            self.stop_server()  # Stop server after scene finishes

    # def start(self):
    #     logger.debug("start()")

    def stop(self):
        logger.debug("stop()")

        for e in self._scheduler.queue:
            self._scheduler.cancel(e)

        if self._sonos_soco:
            self._sonos_soco.stop()
        if self._audioproc:
            self._audioproc.kill()

        self.stop_server()

    def reset(self):
        logger.debug("reset()")

        self.stop()

        # # Turn off all the lights
        # for light in self._lights:
        #     light.set_light(lamp_on=False)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: sceneplayer.py PATH")
    path = sys.argv[1]

    if not DIRIGERA_TOKEN:
        sys.exit("DIRIGERA_TOKEN env var must be set")
    if not DIRIGERA_IP_ADDRESS:
        sys.exit("DIRIGERA_IP_ADDRESS env var must be set")

    try:
        logger.info(f"Using DIRIGERA at {DIRIGERA_IP_ADDRESS}")
        dirigera_hub = dirigera.Hub(
            token=DIRIGERA_TOKEN, ip_address=DIRIGERA_IP_ADDRESS
        )

        if SONOS_IP_ADDRESS:
            logger.info(f"Using Sonos at {SONOS_IP_ADDRESS}")
            sonos_soco = soco.SoCo(SONOS_IP_ADDRESS)
        else:
            logger.info(f"Looking for Sonos named {SONOS_PLAYER_NAME}")
            zone_set = soco.discover()
            if not zone_set:
                sys.exit("Fatal error while discovering Sonos speakers")
            try:
                sonos_soco = next(
                    zone for zone in zone_set if zone.player_name == SONOS_PLAYER_NAME
                )
            except StopIteration:
                sonos_soco = None
                logger.warning(f"Can't find Sonos speaker named {SONOS_PLAYER_NAME}")

        player = ScenePlayer(dirigera_hub, sonos_soco)
        player.reset()

        player.run(path=path)
    except KeyboardInterrupt:
        player.reset()
