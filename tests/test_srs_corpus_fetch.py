"""No-network tests for the corpus fetcher's licence and provenance contract."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("srs_corpus_tool", ROOT / "tools" / "srs_corpus.py")
assert SPEC and SPEC.loader
corpus_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(corpus_tool)


class CorpusFetchTests(unittest.TestCase):
    def test_reference_only_source_is_refused_before_any_network_request(self):
        with patch.object(corpus_tool, "find_source", return_value={
                "id": "not-licensed", "ingestion": "reference_only"}):
            with self.assertRaisesRegex(ValueError, "reference-only"):
                corpus_tool.fetch("not-licensed", Path(tempfile.mkdtemp()))

    def test_download_writes_hash_licence_and_attribution_receipt(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, size=-1):
                if getattr(self, "sent", False):
                    return b""
                self.sent = True
                return b"licensed corpus sample"

        row = {"id": "sample", "ingestion": "allowed_with_attribution",
               "download_url": "https://example.test/sample.zip", "source_url": "https://example.test",
               "license": "CC-BY-4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
               "attribution": "Example author", "known_checksums": {}}
        with tempfile.TemporaryDirectory() as tmp, patch.object(corpus_tool, "find_source", return_value=row), \
                patch.object(corpus_tool, "urlopen", return_value=Response()):
            record = corpus_tool.fetch("sample", Path(tmp))
            receipt = Path(tmp) / "sample" / "receipt.json"
            self.assertTrue(receipt.is_file())
            self.assertEqual(json.loads(receipt.read_text(encoding="utf-8"))["checksums"]["sha256"],
                             record["checksums"]["sha256"])
            self.assertEqual(record["attribution"], "Example author")

    def test_inspect_reports_archive_shape_without_extracting_it(self):
        import zipfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sample"
            root.mkdir()
            archive = root / "sample.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("documents/one.xml", "<doc />")
                bundle.writestr("__MACOSX/ignored", "x")
            (root / "receipt.json").write_text(json.dumps({"filename": archive.name}), encoding="utf-8")
            with patch.object(corpus_tool, "find_source", return_value={"scale": {}}):
                report = corpus_tool.inspect("sample", Path(tmp))
            self.assertEqual(report["files"], 1)
            self.assertEqual(report["document_files"], 1)

    def test_inspect_counts_arff_data_rows_without_returning_requirement_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "sample"
            root.mkdir()
            source = root / "sample.arff"
            source.write_text("@RELATION test\n@DATA\nfirst\nsecond\n", encoding="utf-8")
            (root / "receipt.json").write_text(json.dumps({"filename": source.name}), encoding="utf-8")
            with patch.object(corpus_tool, "find_source", return_value={"scale": {"requirements": 2}}):
                report = corpus_tool.inspect("sample", Path(tmp))
            self.assertEqual(report["format"], "arff")
            self.assertEqual(report["data_rows"], 2)
            self.assertNotIn("first", json.dumps(report))

    def test_build_evaluation_creates_one_hundred_balanced_cases_with_a_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "promise-exp"
            root.mkdir()
            raw = root / "sample.arff"
            labels = ("F", "PE", "SE", "US")
            records = "\n".join(
                f"1,'The system shall complete item {number} within {number} ms.',{labels[number % len(labels)]}"
                for number in range(120))
            raw.write_text("@RELATION test\n@DATA\n" + records + "\n", encoding="utf-8")
            (root / "receipt.json").write_text(json.dumps({"filename": raw.name,
                "checksums": {"sha256": "source-hash"}}), encoding="utf-8")
            source = {"id": "promise-exp", "ingestion": "allowed_with_attribution_and_share_alike",
                      "license": "CC-BY-SA-3.0", "attribution": "Example"}
            with patch.object(corpus_tool, "find_source", return_value=source):
                result = corpus_tool.build_evaluation("promise-exp", 100, Path(tmp))
            self.assertEqual(result["size"], 100)
            self.assertTrue((Path(tmp) / "evaluations" / "promise-exp-100.jsonl").is_file())
            self.assertEqual(set(result["label_counts"]), set(labels))
