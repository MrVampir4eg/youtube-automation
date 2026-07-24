import unittest

from src.free_content_generator import FreeContentGenerator


class CompatibilityTests(unittest.TestCase):
    def test_quality_feedback_fallback_is_available(self):
        generator = FreeContentGenerator()
        feedback = generator._quality_feedback({"hook": "", "body": ""})

        self.assertIn("хук", feedback)
        self.assertIn("розвиток", feedback)


if __name__ == "__main__":
    unittest.main()
