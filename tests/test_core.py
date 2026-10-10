from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tutor_app.course import (
    CourseError,
    create_sample_course,
    make_lesson_notes,
    validate_course,
)
from tutor_app.configuration import resolve_gemini_api_key
from tutor_app.gemini import GeminiError, answer_question
from tutor_app.media import make_video
from tutor_app.security import ProfileError
from tutor_app.storage import Repository


class SecurityAndStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database = Path(self.temporary_directory.name) / "learning.sqlite3"
        self.repository = Repository(self.database)

    def test_profile_records_are_encrypted_and_persist(self) -> None:
        profile_id, key, created = self.repository.unlock_or_create(
            "sample_learner", "this is a strong example passphrase", "this is a strong example passphrase"
        )
        self.assertTrue(created)
        self.repository.put(profile_id, key, "profile", "settings", {"goal": "learn safely"})
        self.assertEqual(
            self.repository.get(profile_id, key, "profile", "settings"),
            {"goal": "learn safely"},
        )
        raw_database = self.database.read_bytes()
        self.assertNotIn(b"learn safely", raw_database)
        unlocked_id, unlocked_key, new_profile = self.repository.unlock_or_create(
            "SAMPLE_LEARNER", "this is a strong example passphrase", "unused for existing profiles"
        )
        self.assertFalse(new_profile)
        self.assertEqual(unlocked_id, profile_id)
        self.assertEqual(
            self.repository.get(unlocked_id, unlocked_key, "profile", "settings"),
            {"goal": "learn safely"},
        )

    def test_wrong_passphrase_is_rejected(self) -> None:
        self.repository.unlock_or_create(
            "learner", "a sufficiently strong passphrase", "a sufficiently strong passphrase"
        )
        with self.assertRaises(ProfileError):
            self.repository.unlock_or_create("learner", "a completely wrong passphrase", "")

    def test_profile_delete_removes_vault_and_records(self) -> None:
        profile_id, key, _ = self.repository.unlock_or_create(
            "learner", "a sufficiently strong passphrase", "a sufficiently strong passphrase"
        )
        self.repository.put(profile_id, key, "progress", "sample", [1, 2])
        self.repository.delete_profile(profile_id)
        self.assertIsNone(self.repository.get(profile_id, key, "progress", "sample"))


class CourseTests(unittest.TestCase):
    def test_sample_has_lesson_quiz_and_explicit_sample_label(self) -> None:
        course = create_sample_course()
        lesson = course["lessons"][0]
        self.assertFalse(course["ai_generated"])
        self.assertEqual(len(course["lessons"]), 2)
        self.assertGreaterEqual(len(lesson["quiz"]), 2)
        notes = make_lesson_notes(course, lesson)
        self.assertIn("offline sample (not AI-generated)", notes)
        self.assertIn("Worked example", notes)

    def test_course_rejects_out_of_range_quiz_answer(self) -> None:
        with self.assertRaises(CourseError):
            validate_course(
                {
                    "title": "Course",
                    "summary": "Summary",
                    "lessons": [
                        {
                            "title": "Lesson",
                            "objective": "Objective",
                            "concepts": ["Idea"],
                            "explanation": "Explain",
                            "example": "Example",
                            "quiz": [{
                                "question": "Question?",
                                "options": ["A", "B"],
                                "answer_index": 2,
                                "explanation": "Reason",
                            }],
                        }
                    ],
                },
                "Goal",
                True,
            )

    def test_sample_lesson_renders_a_playable_mp4(self) -> None:
        course = create_sample_course()
        video = make_video(course, course["lessons"][0])
        self.assertGreater(len(video), 1000)
        self.assertEqual(video[4:8], b"ftyp")


class GeminiTests(unittest.TestCase):
    def test_api_key_reads_exact_secret_name(self) -> None:
        self.assertEqual(
            resolve_gemini_api_key({}, {"Gemini API key": "  test-secret  "}),
            "test-secret",
        )

    def test_api_key_preserves_environment_and_legacy_secret_support(self) -> None:
        self.assertEqual(
            resolve_gemini_api_key(
                {"GEMINI_API_KEY": "env-secret"},
                {"Gemini API key": "new-secret", "GEMINI_API_KEY": "legacy-secret"},
            ),
            "env-secret",
        )
        self.assertEqual(
            resolve_gemini_api_key({}, {"GEMINI_API_KEY": "legacy-secret"}),
            "legacy-secret",
        )
        self.assertEqual(resolve_gemini_api_key({}, None), "")

    @patch("tutor_app.gemini.requests.post")
    def test_tutor_includes_lesson_and_recent_context_without_key_in_url(self, post: Mock) -> None:
        response = Mock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "A feature is an input detail."}]}}]
        }
        post.return_value = response
        answer = answer_question(
            "private-test-key",
            {"title": "Sample course", "goal": "Learn the basics"},
            {
                "title": "Features",
                "objective": "Know what a feature is",
                "concepts": ["features"],
                "explanation": "Inputs help a model.",
                "example": "Distance is a feature.",
            },
            "What was the example?",
            [{"role": "user", "text": "What is a feature?"}, {"role": "assistant", "text": "An input."}],
            "Example first",
        )
        self.assertEqual(answer, "A feature is an input detail.")
        args, kwargs = post.call_args
        self.assertNotIn("private-test-key", args[0])
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "private-test-key")
        body = kwargs["json"]
        content = json.dumps(body)
        self.assertIn("Sample course", content)
        self.assertIn("What is a feature?", content)
        self.assertIn("What was the example?", content)

    @patch("tutor_app.gemini.requests.post")
    def test_gemini_rejects_unauthorized_response_without_revealing_key(self, post: Mock) -> None:
        response = Mock()
        response.status_code = 403
        response.ok = False
        post.return_value = response
        with self.assertRaisesRegex(GeminiError, "rejected the API key"):
            answer_question(
                "secret", {"title": "Course", "goal": "Learn"},
                {
                    "title": "Lesson", "objective": "Goal", "concepts": ["idea"],
                    "explanation": "Text", "example": "Example",
                },
                "Question", [], "Example first",
            )


if __name__ == "__main__":
    unittest.main()
