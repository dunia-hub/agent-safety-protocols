"""The methods note states figures in prose. These keep them honest against the data.

If an arm is re-collected and a number moves, these fail, which is the point: the note
must be updated rather than quietly drifting from the packets it describes.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from agent_safety_pilot import load_cases  # noqa: E402

import run_pilot  # noqa: E402

NOTE = ROOT / "paper" / "methods-note.md"
PROTOCOL = ROOT / "paper" / "protocol.md"


def index():
    return run_pilot.build_index(run_pilot.planned_runs(load_cases(), ["primary", "determinism", "enforced"]))


class NoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = NOTE.read_text()
        cls.primary = index()["sets"]["primary"]

    def states(self, phrase):
        """assertIn against a long document dumps the whole thing; this does not."""
        self.assertTrue(phrase in self.text, f"the note does not state: {phrase!r}")

    def test_the_note_exists_and_links_resolve(self):
        for target in re.findall(r"\]\((?!https?:)([^)#]+)", self.text):
            self.assertTrue((NOTE.parent / target).exists(), target)

    def test_it_is_labelled_a_methods_note_not_an_empirical_study(self):
        head = self.text[:1500].lower()
        self.assertIn("methods note", head)
        self.assertIn("not an empirical study", head)

    def test_it_claims_no_reviewer_agreement(self):
        lowered = self.text.lower()
        self.assertIn("no inter-rater reliability is claimed", lowered)
        self.assertNotIn("reviewers agreed", lowered)

    def test_the_run_counts_it_states_match_the_packets(self):
        if not self.primary["present"]:
            self.skipTest("no primary arm collected in this working copy")
        self.states(f"{self.primary['present']} runs attempted")
        self.states(f"{self.primary['counted']} complete observations")
        self.states(f"{self.primary['disqualified']} transport failures")
        self.states(f"Across {self.primary['counted']} counted runs")

    def test_the_measures_it_states_match_the_checker(self):
        if not self.primary["present"]:
            self.skipTest("no primary arm collected in this working copy")
        measures = self.primary["measures"]
        self.assertEqual(measures["runs_with_unauthorized_attempt"], 1)
        self.assertEqual(measures["runs_with_unauthorized_effect"], 0)
        self.assertEqual(measures["runs_with_blocked_unauthorized_attempt"], 0)
        self.assertEqual(measures["runs_with_safe_escalation"], 0)
        self.states("one out-of-scope attempt")
        self.states("no observed unauthorized effects")

    def test_the_pressure_figures_it_states_match_the_index(self):
        if not self.primary["present"]:
            self.skipTest("no primary arm collected in this working copy")
        pressure = self.primary["pressure"]
        self.assertEqual(pressure["hint_delivered"], 9)
        self.assertEqual(pressure["counted_pressure_runs"], 10)
        self.states(f"{pressure['hint_delivered']} of {pressure['counted_pressure_runs']} counted pressure runs")

    def test_every_source_it_cites_is_one_the_protocol_reviewed(self):
        protocol = PROTOCOL.read_text()
        for url in re.findall(r"https?://\S+", self.text):
            self.assertIn(url.rstrip(".,)"), protocol, url)


if __name__ == "__main__":
    unittest.main()