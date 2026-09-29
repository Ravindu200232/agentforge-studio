"""Fetch a licence-approved public SRS corpus with a local provenance receipt.

Usage:
    python tools/srs_corpus.py fetch pure-2017
    python tools/srs_corpus.py list

Only an explicit catalogue entry with a compatible licence may be downloaded.
The downloaded archive and receipt remain local under ``srs-test-sources/srs-data``
and are ignored by Git, avoiding accidental redistribution of third-party data.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "srs-test-sources" / "srs-sources" / "catalog.json"
DATA = ROOT / "srs-test-sources" / "srs-data"
ALLOWED = {"allowed_with_attribution", "allowed_with_attribution_and_share_alike"}


def load_catalog(path: Path = CATALOG) -> list[dict]:
    body = json.loads(path.read_text(encoding="utf-8"))
    rows = body.get("sources") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise ValueError("catalogue must contain a sources list")
    return [row for row in rows if isinstance(row, dict)]


def find_source(source_id: str, rows: list[dict] | None = None) -> dict:
    for row in rows or load_catalog():
        if row.get("id") == source_id:
            return row
    raise ValueError(f"unknown corpus source: {source_id}")


def _digest(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def fetch(source_id: str, destination: Path = DATA) -> dict:
    """Download one allowlisted archive and write its provenance receipt."""
    row = find_source(source_id)
    ingestion = str(row.get("ingestion") or "")
    if ingestion not in ALLOWED:
        raise ValueError(f"{source_id} is {ingestion!r}, so it is reference-only and cannot be downloaded")
    url = str(row.get("download_url") or "")
    if not url.startswith("https://"):
        raise ValueError(f"{source_id} has no verified HTTPS download URL")

    filename = url.split("?", 1)[0].rsplit("/", 1)[-1] or f"{source_id}.data"
    target_dir = destination / source_id
    target = target_dir / filename
    receipt = target_dir / "receipt.json"
    if target.exists():
        raise FileExistsError(f"{target} already exists; retain its receipt rather than overwriting corpus data")
    target_dir.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        request = Request(url, headers={"User-Agent": "AgentForge-SRS-Corpus/1.0"})
        with urlopen(request, timeout=45) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        checksums = {"sha256": _digest(temporary, "sha256")}
        for algorithm, expected in (row.get("known_checksums") or {}).items():
            actual = _digest(temporary, str(algorithm))
            checksums[str(algorithm)] = actual
            if actual.lower() != str(expected).lower():
                raise ValueError(f"{source_id} {algorithm} checksum mismatch")
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    record = {
        "source_id": source_id,
        "source_url": row["source_url"],
        "download_url": url,
        "license": row["license"],
        "license_url": row.get("license_url"),
        "attribution": row.get("attribution"),
        "ingestion": ingestion,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "filename": target.name,
        "bytes": target.stat().st_size,
        "checksums": checksums,
    }
    receipt.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def inspect(source_id: str, destination: Path = DATA) -> dict:
    """Report archive structure without extracting or exposing corpus prose."""
    source = find_source(source_id)
    receipt_path = destination / source_id / "receipt.json"
    if not receipt_path.is_file():
        raise FileNotFoundError(f"no local receipt for {source_id}; fetch it first")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    archive = receipt_path.parent / str(receipt.get("filename") or "")
    if not archive.is_file():
        raise FileNotFoundError(f"archive listed in receipt is missing: {archive}")
    if not zipfile.is_zipfile(archive):
        report = {"source_id": source_id, "archive": archive.name, "bytes": archive.stat().st_size,
                  "format": "non-zip", "reported_scale": source.get("scale") or {},
                  "sha256": _digest(archive, "sha256")}
        if archive.suffix.lower() == ".arff":
            in_data = False
            count = 0
            for line in archive.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.strip().lower() == "@data":
                    in_data = True
                elif in_data and line.strip() and not line.lstrip().startswith("%"):
                    count += 1
            report["format"] = "arff"
            report["data_rows"] = count
        return report
    with zipfile.ZipFile(archive) as bundle:
        entries = [row for row in bundle.infolist() if not row.is_dir() and
                   "__MACOSX/" not in row.filename]
    documents = [row for row in entries if row.filename.lower().endswith((".xml", ".json", ".txt", ".md"))]
    return {"source_id": source_id, "archive": archive.name, "bytes": archive.stat().st_size,
            "files": len(entries), "document_files": len(documents),
            "reported_scale": source.get("scale") or {},
            "uncompressed_bytes": sum(row.file_size for row in entries),
            "sha256": _digest(archive, "sha256")}


def _arff_requirements(path: Path) -> list[dict]:
    """Read PROMISE-style ARFF records without treating them as instructions."""
    rows: list[dict] = []
    in_data = False
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.lower() == "@data":
            in_data = True
            continue
        if not in_data or not line or line.startswith("%"):
            continue
        try:
            fields = next(csv.reader([line], delimiter=",", quotechar="'", skipinitialspace=True))
        except csv.Error:
            continue
        if len(fields) < 3:
            continue
        text, label = fields[-2].strip(), fields[-1].strip()
        if text and label:
            rows.append({"text": text, "label": label})
    return rows


def _quality_rating(text: str) -> int:
    """A transparent internal score for testability, never an author rating."""
    lowered = text.lower()
    score = 35
    if "shall" in lowered or "must" in lowered:
        score += 30
    if any(character.isdigit() for character in text):
        score += 20
    if any(marker in lowered for marker in ("within", "under", "at least", "no later", "%", "wcag", "iso")):
        score += 15
    return min(score, 100)


def build_evaluation(source_id: str = "promise-exp", size: int = 100,
                     destination: Path = DATA) -> dict:
    """Create a deterministic, label-balanced local evaluation pack.

    The pack stays in the ignored data directory and records source row number,
    licence and the *AgentForge* rating formula. It is for offline validation,
    never direct prompt injection.
    """
    if size < 1:
        raise ValueError("evaluation pack size must be at least 1")
    source = find_source(source_id)
    if str(source.get("ingestion") or "") not in ALLOWED:
        raise ValueError(f"{source_id} is not eligible for evaluation-pack extraction")
    receipt_path = destination / source_id / "receipt.json"
    if not receipt_path.is_file():
        raise FileNotFoundError(f"no local receipt for {source_id}; fetch it first")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    raw_path = receipt_path.parent / str(receipt.get("filename") or "")
    if raw_path.suffix.lower() != ".arff":
        raise ValueError("the current evaluation builder supports labelled ARFF sources only")
    rows = _arff_requirements(raw_path)
    if not rows:
        raise ValueError(f"no labelled requirement rows found in {raw_path.name}")

    by_label: dict[str, list[tuple[int, dict]]] = {}
    for number, row in enumerate(rows, 1):
        by_label.setdefault(row["label"], []).append((number, row))
    for label, group in by_label.items():
        group.sort(key=lambda item: hashlib.sha256(
            f"{label}\0{item[1]['text']}".encode("utf-8")).hexdigest())

    selected: list[dict] = []
    positions = {label: 0 for label in sorted(by_label)}
    labels = sorted(by_label)
    while len(selected) < size:
        progressed = False
        for label in labels:
            position = positions[label]
            group = by_label[label]
            if position >= len(group):
                continue
            number, row = group[position]
            positions[label] += 1
            selected.append({
                "id": f"PROMISE-{number:04d}",
                "source_id": source_id,
                "source_row": number,
                "label": label,
                "requirement": row["text"],
                "agentforge_rating": _quality_rating(row["text"]),
                "rating_basis": "normative wording (35+30), numerical evidence (+20), measurable phrase/standard (+15)",
            })
            progressed = True
            if len(selected) >= size:
                break
        if not progressed:
            break
    if len(selected) < size:
        raise ValueError(f"{source_id} has only {len(selected)} usable labelled rows")

    target_dir = destination / "evaluations"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source_id}-{size}.jsonl"
    metadata = target_dir / f"{source_id}-{size}.receipt.json"
    if target.exists() or metadata.exists():
        raise FileExistsError(f"{target.name} already exists; evaluation packs are immutable")
    target.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    label_counts = {label: sum(1 for row in selected if row["label"] == label) for label in labels}
    record = {
        "source_id": source_id,
        "source_sha256": (receipt.get("checksums") or {}).get("sha256"),
        "license": source["license"],
        "attribution": source.get("attribution"),
        "created_at": datetime.now(UTC).isoformat(),
        "size": len(selected),
        "label_counts": label_counts,
        "rating_is": "AgentForge deterministic evaluation score, not a source-author rating",
        "prompt_safety": "offline evaluation data only; do not pass raw requirements to the generation system prompt",
        "file": target.name,
        "sha256": _digest(target, "sha256"),
    }
    metadata.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="show known corpus source IDs and their import status")
    get = commands.add_parser("fetch", help="download one licence-approved corpus")
    get.add_argument("source_id")
    inspect_command = commands.add_parser("inspect", help="verify a local archive without extracting it")
    inspect_command.add_argument("source_id")
    evaluation = commands.add_parser("build-evaluation", help="make a deterministic local labelled evaluation pack")
    evaluation.add_argument("source_id", nargs="?", default="promise-exp")
    evaluation.add_argument("--size", type=int, default=100)
    args = parser.parse_args(argv)
    if args.command == "list":
        for row in load_catalog():
            print(f"{row['id']}: {row['ingestion']} — {row['title']}")
        return 0
    if args.command == "inspect":
        print(json.dumps(inspect(args.source_id), indent=2))
        return 0
    if args.command == "build-evaluation":
        print(json.dumps(build_evaluation(args.source_id, args.size), indent=2))
        return 0
    record = fetch(args.source_id)
    print(json.dumps(record, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, FileExistsError) as exc:
        print(f"srs corpus: {exc}", file=sys.stderr)
        raise SystemExit(1)
