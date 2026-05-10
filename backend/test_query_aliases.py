"""Unit-Tests für query_aliases (ohne Chroma/Flask)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from query_aliases import (
    MAX_EXTRA_SYNONYM_TOKENS,
    MAX_RELATED_PER_TOKEN,
    active_canonical_targets,
    build_canonical_query_variant,
    build_merged_store,
    canonical_match_bonus,
    expand_query_tokens,
    normalize_text,
    reset_query_aliases_cache,
)


class TestNormalize(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_text("Größen"), "groessen")


class TestExpandQueryTokens(unittest.TestCase):
    def test_per_token_cap(self):
        huge_list = [f"word{i:03d}" for i in range(20)]
        related = {"core": huge_list}
        raw = ["core"]
        stop = set()
        out = expand_query_tokens(raw, related, stop)
        added = set(out) - {"core"}
        self.assertLessEqual(len(added), MAX_RELATED_PER_TOKEN)

    def test_global_cap(self):
        related = {
            "aaaa": ["bbbb", "cccc", "dddd"],
            "eeee": ["ffff", "gggg", "hhhh"],
            "iiii": ["jjjj", "kkkk", "llll"],
            "mmmm": ["nnnn", "oooo", "pppp"],
            "qqqq": ["rrrr", "ssss", "tttt"],
        }
        raw = ["aaaa", "eeee", "iiii", "mmmm", "qqqq"]
        stop = set()
        out = expand_query_tokens(raw, related, stop)
        base = set(raw)
        added = len(set(out) - base)
        self.assertLessEqual(added, MAX_EXTRA_SYNONYM_TOKENS)


class TestMergedStore(unittest.TestCase):
    def test_json_overrides_legacy_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aliases.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 42,
                        "related_tokens": {"mathe": ["allein_recht"]},
                        "alias_to_canonical": {},
                    }
                ),
                encoding="utf-8",
            )
            reset_query_aliases_cache()
            store = build_merged_store(path)
            self.assertEqual(store["version"], 42)
            self.assertEqual(store["related_tokens"]["mathe"], ["allein_recht"])


class TestCanonical(unittest.TestCase):
    def test_variant_replaces_word(self):
        alias_map = {"mathe": "mathematik"}
        v = build_canonical_query_variant("aufgaben mathe klasse", alias_map)
        self.assertIsNotNone(v)
        self.assertIn("mathematik", normalize_text(v))
        self.assertNotIn(" mathe ", " " + normalize_text(v) + " ")

    def test_active_targets(self):
        t = active_canonical_targets("mathe zahlen", {"mathe": "mathematik"})
        self.assertEqual(t, {"mathematik"})

    def test_bonus(self):
        b = canonical_match_bonus("die mathematik vertiefen", {"mathematik"})
        self.assertGreater(b, 0)
        self.assertLessEqual(b, 0.05)


if __name__ == "__main__":
    unittest.main()
