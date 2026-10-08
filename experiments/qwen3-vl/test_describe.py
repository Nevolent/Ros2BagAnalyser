"""Synthetic checks for the experiment's JSON output contract."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import describe


class DescriptionResultTests(unittest.TestCase):
    def evidence(self, **changes):
        values = {
            "environment": "an indoor test area with gravel-like terrain, dark curtains and artificial lighting",
            "objects": ["a white spherical object", "several rectangular blocks"],
            "gravel_like_terrain": True,
            "dark_curtains": True,
            "artificial_lighting": True,
            "other_robots_visible": False,
            "people_visible": False,
            "independent_movement_visible": False,
        }
        values.update(changes)
        return json.dumps(values)

    def test_two_sentence_bunker_result(self):
        result = describe.validated_result(self.evidence())
        self.assertEqual(result, {
            "description": (
                "An indoor test area with gravel-like terrain, dark curtains and "
                "artificial lighting, featuring a white spherical object and several "
                "rectangular blocks. No other robots, people, or active movement "
                "are visible."
            ),
            "bunker": True,
        })

    def test_every_bunker_cue_is_required(self):
        for missing in ("gravel_like_terrain", "dark_curtains", "artificial_lighting"):
            with self.subTest(missing=missing):
                result = describe.validated_result(self.evidence(**{missing: False}))
                self.assertIs(result["bunker"], False)

    def test_visible_activity_and_repeated_background_items(self):
        result = describe.validated_result(self.evidence(
            objects=["lights", "several rectangular blocks"], people_visible=True,
        ))
        self.assertEqual(result["description"], (
            "An indoor test area with gravel-like terrain, dark curtains and "
            "artificial lighting, featuring several rectangular blocks. People are "
            "visible; no other robots or active movement are visible."
        ))

    def test_invalid_json_does_not_replace_saved_result(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(describe, "ROOT", Path(directory)):
                output = describe.save_result(
                    describe.validated_result(self.evidence()), "fixture"
                )
                original = output.read_text()
                with self.assertRaises(ValueError):
                    describe.validated_result(self.evidence(dark_curtains="true"))
                self.assertEqual(output.read_text(), original)


if __name__ == "__main__":
    unittest.main()
