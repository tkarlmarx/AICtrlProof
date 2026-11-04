"""Answer validation in the web app (app/server.py). Scoring itself is tested via grc."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import server  # noqa: E402

Q = {"id": "GOV-1", "type": "attested"}
T = {"id": "ROBUST-1", "type": "tested"}


class ValidateAnswerTest(unittest.TestCase):
    def test_valid_maturity(self):
        self.assertEqual(server.validate_answer(Q, {"maturity": 2, "note": "x"}), ({"maturity": 2, "note": "x"}, None))

    def test_bad_maturity_rejected(self):
        for m in (4, -1, "2", True, None, 1.5):
            with self.subTest(m=m):
                self.assertIsNone(server.validate_answer(Q, {"maturity": m})[0])

    def test_na_needs_note(self):
        self.assertIsNone(server.validate_answer(Q, {"na": True})[0])
        self.assertEqual(server.validate_answer(Q, {"na": True, "note": "not high-risk"})[0],
                         {"na": True, "note": "not high-risk"})

    def test_tested_question_cannot_be_answered(self):
        self.assertIsNone(server.validate_answer(T, {"maturity": 3})[0])


if __name__ == "__main__":
    unittest.main()
