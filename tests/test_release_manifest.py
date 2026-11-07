"""Release evidence: version consistency across the four sources of truth, and the per-file manifest."""
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import helpers

_spec = importlib.util.spec_from_file_location("release_manifest", helpers.ROOT / "tools" / "release_manifest.py")
rm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rm)


def _repo_copy(tmp: Path) -> Path:
    """The files versions() reads, copied so a test can change them."""
    for rel in ("CHANGELOG.md", ".claude-plugin/marketplace.json",
                "plugins/req-analyzer/.claude-plugin/plugin.json", "plugins/req-analyzer/app/reqanalyzer/__init__.py"):
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(helpers.ROOT / rel, tmp / rel)
    return tmp


def _run(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = rm.main(list(argv))
    return code, out.getvalue()


class VersionConsistency(unittest.TestCase):
    def test_this_repo_declares_one_version_everywhere(self):
        self.assertEqual(rm.check(), [])
        found = rm.versions()
        self.assertEqual(len(set(found.values())), 1, found)
        self.assertEqual(_run("--check")[0], 0)

    def test_a_drifted_version_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo_copy(Path(d))
            p = root / "plugins/req-analyzer/.claude-plugin/plugin.json"
            data = json.loads(p.read_text())
            data["version"] = "9.9.9"
            p.write_text(json.dumps(data))
            problems = rm.check(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("versions disagree", problems[0])
            self.assertIn("plugin.json=9.9.9", problems[0])

    def test_a_missing_version_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = _repo_copy(Path(d))
            (root / "plugins/req-analyzer/app/reqanalyzer/__init__.py").write_text('"""no version"""\n')
            self.assertIn("app/reqanalyzer/__init__.py: no version found", rm.check(root))


class Manifest(unittest.TestCase):
    def test_manifest_covers_the_plugin_and_verifies_against_itself(self):
        m = rm.manifest()
        self.assertEqual(m["version"], rm.versions()[".claude-plugin/plugin.json"])
        self.assertIn(".claude-plugin/plugin.json", m["files"])
        self.assertTrue(all(len(h) == 64 for h in m["files"].values()))
        self.assertEqual(rm.verify(m, helpers.ROOT / rm.PLUGIN), [])

    def test_changed_missing_and_extra_files_fail_verification(self):
        with tempfile.TemporaryDirectory() as d:
            plugin = Path(d) / "plugin"
            (plugin / "sub").mkdir(parents=True)
            for name, data in {"a.txt": "a", "sub/b.txt": "b"}.items():
                (plugin / name).write_text(data)
            expected = {"name": "reusefirst", "version": "1.0.0", "files": rm.digest_tree(plugin)}
            self.assertEqual(rm.verify(expected, plugin), [])
            (plugin / "a.txt").write_text("tampered")
            (plugin / "sub/b.txt").unlink()
            (plugin / "new.py").write_text("print('x')")
            (plugin / "__pycache__").mkdir()
            (plugin / "__pycache__/x.pyc").write_bytes(b"\0")   # caches are ignored
            self.assertEqual(rm.verify(expected, plugin),
                             ["missing: sub/b.txt", "changed: a.txt", "not in manifest: new.py"])
            mf = Path(d) / "m.json"
            mf.write_text(json.dumps(expected))
            code, out = _run("--verify", str(mf), "--root", str(plugin))
            self.assertEqual(code, 1)
            self.assertIn("FAILED reusefirst 1.0.0", out)

    def test_cli_writes_and_verifies_a_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            out_file = Path(d) / "manifest.json"
            self.assertEqual(_run("-o", str(out_file))[0], 0)
            code, out = _run("--verify", str(out_file))
            self.assertEqual(code, 0, out)
            self.assertIn("verified reusefirst", out)

    def test_unreadable_manifest_and_bad_root_are_usage_errors(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.json"
            bad.write_text("{not json")
            self.assertEqual(_run("--verify", str(bad))[0], 2)
            good = Path(d) / "m.json"
            good.write_text(json.dumps({"files": {"a": "0" * 64}}))
            self.assertEqual(_run("--verify", str(good), "--root", str(Path(d) / "nope"))[0], 2)
            self.assertEqual(rm.verify({"files": {}}, Path(d)), ["manifest lists no files"])


if __name__ == "__main__":
    unittest.main()
