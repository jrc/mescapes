import logging
import os
import sched
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

import dirigera
import soco
from dotenv import load_dotenv

from audio_server import AudioServer
from light_controller import LightController
from scenefile import SceneFile, scenefile_named

# Load environment configuration
load_dotenv()


@dataclass
class Config:
    dirigera_ip: str | None = os.getenv("DIRIGERA_IP_ADDRESS")
    dirigera_token: str | None = os.getenv("DIRIGERA_TOKEN")
    dirigera_room: str = os.getenv("DIRIGERA_ROOM_NAME", "Bedroom")
    sonos_ip: str | None = os.getenv("SONOS_IP_ADDRESS")
    sonos_name: str = os.getenv("SONOS_PLAYER_NAME", "Bedroom")
    sonos_volume: int = int(os.getenv("SONOS_VOLUME", "25"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")


# Configure logging
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(Config.log_level)


class ScenePlayer:
    """Coordinates playback of light and audio scenes"""

    def __init__(self, config: Config):
        if not config.dirigera_token:
            raise ValueError("DIRIGERA_TOKEN env var must be set")
        if not config.dirigera_ip:
            raise ValueError("DIRIGERA_IP_ADDRESS env var must be set")

        self._config = config

        self._hub = dirigera.Hub(
            token=config.dirigera_token, ip_address=config.dirigera_ip
        )
        self._lightcontroller = LightController(self._hub, config.dirigera_room)

        self._audio = AudioServer()
        self._sonos = self._setup_sonos()
        self._local_audio = None

        self._scheduler = sched.scheduler()

    def _setup_sonos(self) -> Optional[soco.SoCo]:
        """Initialize Sonos speaker"""
        if self._config.sonos_ip:
            logger.info(f"Using Sonos at {self._config.sonos_ip}")
            return soco.SoCo(self._config.sonos_ip)

        logger.info(f"Looking for Sonos named {self._config.sonos_name}")
        zones = soco.discover()
        if not zones:
            logger.warning("No Sonos speakers found")
            return None

        try:
            return next(z for z in zones if z.player_name == self._config.sonos_name)
        except StopIteration:
            logger.warning(f"Sonos speaker '{self._config.sonos_name}' not found")
            return None

    def run(self, path: Optional[str] = None, scene_id: Optional[str] = None):
        """Run a scene from file path or scene ID"""
        scene = scenefile_named(scene_id) if scene_id else SceneFile(path)
        logger.info(f"Running scene: {scene.scene_id}")

        self.stop()  # Ensure clean state
        self._audio.start()

        try:
            self._schedule_actions(scene)
            self._scheduler.run()
        finally:
            self._audio.stop()

    def _schedule_actions(self, scene: SceneFile):
        """Schedule all scene actions"""
        assert scene.timeline, "Scene has no actions"
        assert scene.info, "Scene has no duration info"

        for action in scene.timeline:
            self._scheduler.enter(
                action["Time"], 1, self._execute_action, argument=(action,)
            )

        # Add terminal event to keep scheduler running for full duration
        self._scheduler.enter(scene.info["TimeDuration"], 1, lambda: None)

    def _execute_action(self, action: dict):
        """Execute a single scene action"""
        logger.debug(f"t{action['Time']:.3f}: {action}")

        if action["Type"] == "Audio":
            self._handle_audio(action)
        elif "LightName" in action:
            self._lightcontroller.apply_action(action["LightName"], action)
        else:
            logger.warning(f"Unsupported action type: {action}")

    def _handle_audio(self, action: dict):
        """Handle audio playback through Sonos or local audio"""
        path = action["File"]
        if self._sonos:
            url = self._audio.get_url(path)
            logger.info(f"Playing {url} at volume {self._config.sonos_volume}")
            self._sonos.volume = self._config.sonos_volume
            self._sonos.play_uri(url)
        else:
            self._local_audio = subprocess.Popen(["afplay", path])
            logger.info(f"Playing locally: {path}")

    def stop(self):
        """Stop all ongoing actions"""
        logger.debug("Stopping scene playback")

        # Stop scheduled events
        for event in self._scheduler.queue:
            self._scheduler.cancel(event)

        # Stop audio playback
        if self._sonos:
            self._sonos.stop()
        if self._local_audio:
            self._local_audio.kill()
            self._local_audio = None

        self._audio.stop()


def main():
    """Main entry point for command line usage"""
    if len(sys.argv) < 2:
        sys.exit("usage: sceneplayer.py PATH")

    config = Config()

    try:
        player = ScenePlayer(config)
        player.run(path=sys.argv[1])
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        player.stop()
    except Exception as e:
        logger.error(f"Failed to run scene: {e}")
        raise


if __name__ == "__main__":
    main()
