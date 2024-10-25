import jsonschema

import json
import logging
from pathlib import Path


logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel("INFO")


def scenefile_named(filename):
    path = str(Path("scenes", filename).with_suffix(".json").resolve())
    return SceneFile(path)


class SceneFile:
    def __init__(self, path):
        assert path

        # Public
        self.path = path
        self.scene_id = Path(path).name
        self.info = None
        self.timeline = None

        self._load()

    def _validate(self, root_obj):
        # https://json-schema.org/understanding-json-schema/
        schema = {
            "type": "object",
            "properties": {
                "DisplayName": {"type": "string"},
                "TimeDuration": {"type": "number"},
                "Timeline": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "Time": {"type": "number"},
                            "Type": {"type": "string"},
                        },
                        "required": ["Time", "Type"],
                    },
                },
            },
            "required": ["TimeDuration", "Timeline"],
        }
        jsonschema.validate(instance=root_obj, schema=schema)

        action_dicts = root_obj["Timeline"]
        for action_dict in action_dicts:
            if action_dict["Type"] == "Audio":
                schema = {
                    "type": "object",
                    "properties": {"File": {"type": "string"}},
                    "required": ["File"],
                }
                jsonschema.validate(instance=action_dict, schema=schema)

            if action_dict["Type"] == "Hue":
                schema = {
                    "type": "object",
                    "properties": {
                        "LightName": {"type": "string"},
                        "LightGroup": {"type": "string"},
                        "Hue_on": {"type": "boolean"},
                        "Hue_bri": {"type": "integer"},
                        "Hue_xy": {
                            "type": "array",
                            "items": {"type": "number"},
                            "minItems": 2,
                            "maxItems": 2,
                        },
                        "Hue_transitiontime": {"type": "integer"},
                    },
                }
                jsonschema.validate(instance=action_dict, schema=schema)

    def _load(self):
        with open(self.path) as jsonfile:
            root_obj = json.load(jsonfile)
            self._validate(root_obj)

            self.info = root_obj
            self.timeline = root_obj.pop("Timeline")
