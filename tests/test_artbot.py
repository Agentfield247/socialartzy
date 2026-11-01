"""Unit tests for the queue, caption helpers, rate limiter and posting loop.

They use only the standard library and never touch the network, so they run in
a second and are safe to execute before pushing:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from artbot import common, config, queue_manager  # noqa: E402
from artbot.logging_utils import get_logger  # noqa: E402
from artbot.rate_limiter import DailyCounter  # noqa: E402
from artbot.runner import run_platform  # noqa: E402

HEADER = (
    "id,platform,image_filename,caption,alt_text,hashtags,pinterest_board,"
    "posted_instagram,posted_pinterest,posted,posted_at\n"
)


class TempWorkspace(unittest.TestCase):
    """Points config at a throwaway folder so the real repo files stay clean."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="socialartzy-test-"))
        self.art = self.tmp / "art"
        self.art.mkdir()
        (self.art / "art.png").write_bytes(b"\x89PNG\r\n\x1a\n fake")
        self.queue = self.tmp / "queue.csv"
        self.counter_path = self.tmp / "daily_count.json"

        self._saved = (
            config.ART_DIR,
            config.QUEUE_FILE,
            config.DAILY_COUNTER_FILE,
            config.IG_DAILY_LIMIT,
            config.PINTEREST_DAILY_LIMIT,
        )
        config.ART_DIR = self.art
        config.QUEUE_FILE = self.queue
        config.DAILY_COUNTER_FILE = self.counter_path
        self.logger = get_logger("tests", log_file=self.tmp / "test.log")

    def tearDown(self) -> None:
        (
            config.ART_DIR,
            config.QUEUE_FILE,
            config.DAILY_COUNTER_FILE,
            config.IG_DAILY_LIMIT,
            config.PINTEREST_DAILY_LIMIT,
        ) = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_queue(self, *lines: str) -> None:
        self.queue.write_text(HEADER + "".join(line + "\n" for line in lines), encoding="utf-8")


class QueueTests(TempWorkspace):
    def test_reads_first_pending_row_and_skips_posted(self) -> None:
        self.write_queue(
            "1,both,art.png,First,,#art,Board,,,",
            "2,instagram,art.png,Second,,#art,Board,,,",
        )
        rows = queue_manager.read_queue()
        self.assertEqual([row["id"] for row in rows], ["1", "2"])

        first = queue_manager.find_next(rows, "instagram")
        self.assertEqual(first["id"], "1")

        queue_manager.mark_posted_in_file("1", "instagram")
        rows = queue_manager.read_queue()
        # Row 1 is still pending for Pinterest, but Instagram moves on to row 2.
        self.assertEqual(queue_manager.find_next(rows, "instagram")["id"], "2")
        self.assertEqual(queue_manager.find_next(rows, "pinterest")["id"], "1")
        self.assertFalse(queue_manager.is_posted(rows[0], "pinterest"))

    def test_posted_flag_becomes_true_once_every_platform_is_done(self) -> None:
        self.write_queue("7,both,art.png,Both,,#art,Board,,,")
        queue_manager.mark_posted_in_file("7", "instagram")
        row = queue_manager.read_queue()[0]
        self.assertEqual(row["posted"], "false")
        self.assertTrue(row["posted_at"])

        queue_manager.mark_posted_in_file("7", "pinterest")
        row = queue_manager.read_queue()[0]
        self.assertEqual(row["posted"], "true")
        self.assertEqual(queue_manager.platforms_for(row), ["instagram", "pinterest"])

    def test_platform_aliases_and_single_platform_rows(self) -> None:
        self.write_queue(
            "1,IG,art.png,Insta only,,#art,Board,,,",
            "2,pins,art.png,Pinterest only,,#art,Board,,,",
        )
        rows = queue_manager.read_queue()
        self.assertEqual(queue_manager.platforms_for(rows[0]), ["instagram"])
        self.assertEqual(queue_manager.platforms_for(rows[1]), ["pinterest"])

    def test_write_queue_is_atomic_and_keeps_header(self) -> None:
        self.write_queue("1,both,art.png,Text,,#art,Board,,,")
        rows = queue_manager.read_queue()
        rows[0]["caption"] = "Edited, with a comma"
        queue_manager.write_queue(rows)

        text = self.queue.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(HEADER))
        self.assertIn('"Edited, with a comma"', text)
        self.assertEqual(queue_manager.read_queue()[0]["caption"], "Edited, with a comma")
        self.assertEqual(list(self.tmp.glob(".queue-*")), [])

    def test_validate_reports_missing_image_and_bad_platform(self) -> None:
        self.write_queue("1,tumblr,missing.png,Text,,#art,Board,,,")
        problems = queue_manager.validate(queue_manager.read_queue())
        joined = " | ".join(problems)
        self.assertIn("platform must be", joined)
        self.assertIn("Artwork not found", joined)


class CaptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = get_logger(
            "caption-tests", log_file=Path(tempfile.gettempdir()) / "artbot-test.log"
        )

    def test_hashtags_are_normalised_and_deduplicated(self) -> None:
        self.assertEqual(
            common.normalize_hashtags("art, #painting  #ART #DailyArt"),
            "#art #painting #DailyArt",
        )

    def test_caption_combines_body_and_hashtags(self) -> None:
        caption = common.build_caption(
            "A quiet study.", "art, painting", limit=2200, logger=self.logger
        )
        self.assertEqual(caption, "A quiet study.\n\n#art #painting")

    def test_long_caption_is_trimmed_to_the_limit(self) -> None:
        caption = common.build_caption(
            "word " * 600, "#art", limit=config.IG_CAPTION_LIMIT, logger=self.logger
        )
        self.assertLessEqual(len(caption), config.IG_CAPTION_LIMIT)
        self.assertTrue(caption.endswith("..."))

    def test_title_is_derived_from_the_first_sentence(self) -> None:
        title = common.derive_title("First light over the harbour. Painted on Sunday.", limit=100)
        self.assertEqual(title, "First light over the harbour")

    def test_alt_text_limit_is_respected(self) -> None:
        alt = common.truncate("x " * 900, config.IG_ALT_TEXT_LIMIT)
        self.assertLessEqual(len(alt), config.IG_ALT_TEXT_LIMIT)

    def test_image_resolution_blocks_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "ok.png").write_bytes(b"x")
            self.assertEqual(common.resolve_image("ok.png", art_dir=base).name, "ok.png")
            with self.assertRaises(ValueError):
                common.resolve_image("../secret.png", art_dir=base)
            with self.assertRaises(FileNotFoundError):
                common.resolve_image("nope.png", art_dir=base)


class CounterTests(TempWorkspace):
    def test_counter_resets_on_a_new_day_and_enforces_the_limit(self) -> None:
        counter = DailyCounter(self.counter_path, today="2026-01-11")
        self.assertTrue(counter.can_post("instagram"))

        counter.record("instagram", row_id="1")
        config.IG_DAILY_LIMIT = 1
        self.assertFalse(counter.can_post("instagram"))
        self.assertEqual(counter.remaining("instagram"), 0)

        data = json.loads(self.counter_path.read_text(encoding="utf-8"))
        self.assertEqual(data["date"], "2026-01-11")
        self.assertEqual(data["counts"]["instagram"], 1)

        next_day = DailyCounter(self.counter_path, today="2026-01-12")
        self.assertEqual(next_day.count("instagram"), 0)
        self.assertTrue(next_day.can_post("instagram"))
        self.assertEqual(len(next_day.snapshot()), 2)

    def test_corrupt_counter_file_is_ignored(self) -> None:
        self.counter_path.write_text("{not json", encoding="utf-8")
        counter = DailyCounter(self.counter_path, today="2026-01-11")
        self.assertEqual(counter.count("pinterest"), 0)


class RunnerTests(TempWorkspace):
    def test_successful_post_marks_the_row_and_increments_the_counter(self) -> None:
        self.write_queue("1,both,art.png,Hello,,#art,Board,,,")
        calls = []

        def fake_poster(row, logger=None, dry_run=False):
            calls.append(row["id"])
            return common.PostResult("instagram", common.POSTED, "ok", row["id"], "https://x/p/1")

        results = run_platform("instagram", fake_poster, logger=self.logger)
        self.assertEqual(calls, ["1"])
        self.assertTrue(results[0].posted)

        rows = queue_manager.read_queue()
        self.assertTrue(queue_manager.is_posted(rows[0], "instagram"))
        self.assertFalse(queue_manager.is_posted(rows[0], "pinterest"))
        self.assertEqual(DailyCounter(self.counter_path).count("instagram"), 1)

    def test_daily_limit_stops_the_run_before_posting(self) -> None:
        config.IG_DAILY_LIMIT = 1
        self.write_queue(
            "1,instagram,art.png,Hello,,#art,Board,,,",
            "2,instagram,art.png,Hi,,#art,Board,,,",
        )
        DailyCounter(self.counter_path).record("instagram", row_id="0")

        calls = []

        def fake_poster(row, logger=None, dry_run=False):  # pragma: no cover - must not run
            calls.append(row["id"])
            return common.PostResult("instagram", common.POSTED)

        results = run_platform("instagram", fake_poster, logger=self.logger)
        self.assertEqual(calls, [])
        self.assertEqual(results[0].status, common.SKIPPED)
        self.assertIn("daily instagram limit reached", results[0].message)

    def test_failure_does_not_mark_the_row_as_posted(self) -> None:
        self.write_queue("1,instagram,art.png,Hello,,#art,Board,,,")

        def fake_poster(row, logger=None, dry_run=False):
            return common.PostResult("instagram", common.FAILED, "boom", row["id"])

        results = run_platform("instagram", fake_poster, logger=self.logger)
        self.assertTrue(results[0].failed)
        self.assertFalse(queue_manager.is_posted(queue_manager.read_queue()[0], "instagram"))
        self.assertEqual(DailyCounter(self.counter_path).count("instagram"), 0)

    def test_dry_run_previews_without_touching_the_queue(self) -> None:
        self.write_queue("1,instagram,art.png,Hello,,#art,Board,,,")
        before = self.queue.read_text(encoding="utf-8")

        def fake_poster(row, logger=None, dry_run=False):
            self.assertTrue(dry_run)
            return common.PostResult("instagram", common.DRY_RUN, "preview", row["id"])

        results = run_platform("instagram", fake_poster, logger=self.logger, dry_run=True)
        self.assertEqual(results[0].status, common.DRY_RUN)
        self.assertEqual(self.queue.read_text(encoding="utf-8"), before)

    def test_empty_queue_is_not_an_error(self) -> None:
        self.write_queue("1,instagram,art.png,Hello,,#art,Board,true,,")

        def fake_poster(row, logger=None, dry_run=False):  # pragma: no cover - must not run
            return common.PostResult("instagram", common.POSTED)

        results = run_platform("instagram", fake_poster, logger=self.logger)
        self.assertEqual(results[0].status, common.SKIPPED)
        self.assertIn("no pending rows", results[0].message)


if __name__ == "__main__":
    unittest.main(verbosity=2)