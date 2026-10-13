"""Keep personal data out of what is sent to the model.

Whatever the person types - the idea, an answer in the interview, a request in the chat, the reply to a question - goes through
Microsoft Presidio first. Presidio's analyzer finds the personal data in the text (names, email addresses, phone numbers,
card and bank numbers, national identity numbers, public IP addresses, ...) and its anonymizer replaces each one with a
placeholder such as `<EMAIL_ADDRESS>` or `<PERSON_2>`, so the model, the project's logs and the chat history only ever see the
placeholder. The chat says what was hidden (how many of which kind, never the values).

Presidio finds names with a small spaCy English model (`en_core_web_sm`, set with `privacy_model`) and everything else with
its pattern recognizers, which do not depend on the language the message is written in, so an email address or a phone number
is found in a Sinhala or a Singlish message too. Two recognizers are added for Sri Lanka: its national identity number in both
forms, and its phone numbers. Without the spaCy model Presidio runs on its pattern recognizers alone.

If Presidio itself is not installed the message is not sent at all (`NotSent`) and the person is told how to fix that: a filter
that quietly lets everything through is worse than none. Turning the filter off is the person's own choice (`privacy_filter`).

What is not covered: a credential is not personal data in Presidio's sense - `secrets_guard.py` refuses those before this runs -
and files the person attaches are read by the agent as they are.
"""
from __future__ import annotations

import ipaddress
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from . import bus, config

# What is hidden unless `privacy_entities` says otherwise: the things that identify a person. Places, organisations, dates and
# web addresses are left alone: an app for a hotel in Colombo needs "Colombo", and none of them identify anyone alone.
DEFAULT_ENTITIES = (
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "IBAN_CODE", "IP_ADDRESS", "CRYPTO", "MEDICAL_LICENSE",
    "US_SSN", "US_ITIN", "US_PASSPORT", "US_BANK_NUMBER", "US_DRIVER_LICENSE", "UK_NHS", "LK_NIC",
)
MIN_SCORE = 0.4                  # Presidio's own advice is 0.4 to 0.5; below it a match is mostly noise
MODEL = "en_core_web_sm"
CHUNK = 50_000                   # characters analysed at a time
LABELS = {                       # entity -> (one, many), for the line in the chat
    "PERSON": ("name", "names"), "EMAIL_ADDRESS": ("email address", "email addresses"),
    "PHONE_NUMBER": ("phone number", "phone numbers"), "CREDIT_CARD": ("card number", "card numbers"),
    "IBAN_CODE": ("bank account (IBAN)", "bank accounts (IBAN)"), "IP_ADDRESS": ("IP address", "IP addresses"),
    "CRYPTO": ("crypto wallet", "crypto wallets"), "MEDICAL_LICENSE": ("medical licence number", "medical licence numbers"),
    "US_SSN": ("social security number", "social security numbers"), "US_ITIN": ("tax number", "tax numbers"),
    "US_PASSPORT": ("passport number", "passport numbers"), "US_BANK_NUMBER": ("bank account number", "bank account numbers"),
    "US_DRIVER_LICENSE": ("driving licence number", "driving licence numbers"), "UK_NHS": ("NHS number", "NHS numbers"),
    "LK_NIC": ("national identity number", "national identity numbers"),
}
PHONE_REGIONS = ("LK", "US", "GB", "IN", "AU", "CA", "DE", "FR", "AE", "SG")
# Addresses that are reserved for examples (RFC 2606) are what people write as sample data, not a person's own.
_EXAMPLE_EMAIL = re.compile(r"@(?:[a-z0-9-]+\.)*(?:example\.(?:com|org|net)|[a-z0-9-]+\.(?:test|invalid|localhost|example))$|@localhost$",
                            re.IGNORECASE)
INSTALL = "python -m pip install presidio-analyzer presidio-anonymizer spacy` and `python -m spacy download en_core_web_sm"


class NotSent(ValueError):
    """The message was held back because the privacy filter could not run."""


@dataclass
class Scrubbed:
    text: str
    found: dict[str, int] = field(default_factory=dict)       # entity -> how many were hidden

    @property
    def changed(self) -> bool:
        return bool(self.found)


_lock = threading.Lock()
_ready: dict[str, Any] = {}


def enabled() -> bool:
    return bool(config.setting("privacy_filter", True))


def entities() -> tuple[str, ...]:
    chosen = config.setting("privacy_entities", None)
    rows = tuple(str(item).strip().upper() for item in chosen if str(item).strip()) if isinstance(chosen, (list, tuple)) else ()
    return rows or DEFAULT_ENTITIES


def _model() -> str:
    return str(config.setting("privacy_model", MODEL) or MODEL).strip()


# --- Presidio -----------------------------------------------------------------------------------------------------------

def _build() -> dict[str, Any]:
    try:
        import spacy
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
        from presidio_analyzer.nlp_engine import NlpEngineProvider, SpacyNlpEngine
        from presidio_analyzer.predefined_recognizers import PhoneRecognizer
        from presidio_anonymizer import AnonymizerEngine
    except ImportError as exc:
        if "DLL load failed" in str(exc):
            raise NotSent(
                "The privacy filter's Windows runtime could not load, so nothing you type is sent to the model. "
                "Update or reinstall AgentForge, then try again. "
                f"({exc})") from exc
        raise NotSent(
            "The privacy filter (Microsoft Presidio) is not installed, so nothing you type is sent to the model. "
            f"Run studio.bat again (it installs what is missing), or install it with `{INSTALL}`, or turn the filter off in the "
            f"studio's settings (privacy_filter). ({exc})") from exc

    class PatternsOnly(SpacyNlpEngine):
        """Presidio on its pattern recognizers alone: no model to find names with."""

        def load(self) -> None:
            nlp = spacy.blank("en")
            nlp.add_pipe("sentencizer")
            self.nlp = {"en": nlp}

    model = _model()
    if spacy.util.is_package(model):
        nlp_engine = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": model}]}).create_engine()
        used = model
    else:
        nlp_engine, used = PatternsOnly(), ""
        nlp_engine.load()
    registry = RecognizerRegistry(supported_languages=["en"])
    registry.load_predefined_recognizers(languages=["en"], nlp_engine=nlp_engine)
    registry.remove_recognizer("PhoneRecognizer")
    registry.add_recognizer(PhoneRecognizer(supported_regions=PHONE_REGIONS))
    registry.add_recognizer(PatternRecognizer(
        supported_entity="LK_NIC", name="LkNicRecognizer", supported_language="en",
        patterns=[Pattern("old NIC", r"\b\d{9}[VvXx]\b", 0.85), Pattern("new NIC", r"\b(?:19|20)\d{10}\b", 0.5)],
        context=["nic", "national identity", "identity card", "id number", "id no"]))
    analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["en"])
    return {"analyzer": analyzer, "anonymizer": AnonymizerEngine(), "model": used}


def _engines() -> dict[str, Any]:
    with _lock:
        if not _ready:
            _ready.update(_build())
        return _ready


def warm_up() -> None:
    """Load Presidio in the background (a few seconds) so that the first message does not wait for it."""
    def load() -> None:
        try:
            _engines()
        except Exception:  # noqa: BLE001 - said when a message needs it
            pass
    threading.Thread(target=load, name="privacy-warm-up", daemon=True).start()


def status() -> dict[str, Any]:
    """What the studio can show about the filter."""
    answer: dict[str, Any] = {"enabled": enabled(), "engine": "Microsoft Presidio", "entities": list(entities()),
                              "ready": False, "model": "", "detail": ""}
    if not answer["enabled"]:
        answer["detail"] = "The privacy filter is turned off."
        return answer
    try:
        engines = _engines()
    except NotSent as exc:
        answer["detail"] = str(exc)
        return answer
    answer.update(ready=True, model=engines["model"],
                  detail="" if engines["model"] else "Names are not found: the spaCy model is not installed, patterns only.")
    return answer


# --- the filter ---------------------------------------------------------------------------------------------------------

def _keep(entity: str, value: str) -> bool:
    """Whether what was found is not personal data after all: sample data, or an address of this computer or network."""
    if entity == "EMAIL_ADDRESS":
        return bool(_EXAMPLE_EMAIL.search(value.strip()))
    if entity == "IP_ADDRESS":
        try:
            address = ipaddress.ip_address(value.strip().strip("[]"))
        except ValueError:
            return False
        return not address.is_global
    return False


def _analyse(analyzer: Any, text: str) -> list[Any]:
    found: list[Any] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK)
        if end < len(text):
            cut = max(text.rfind("\n", start, end), text.rfind(" ", start, end))
            end = cut + 1 if cut > start else end
        for row in analyzer.analyze(text=text[start:end], language="en", entities=list(entities()), score_threshold=MIN_SCORE):
            row.start += start
            row.end += start
            found.append(row)
        start = end
    return found


def _chosen(text: str, rows: list[Any]) -> list[Any]:
    """What is hidden: the wanted kinds, above the score, not sample data; where two overlap, the surer one."""
    wanted = set(entities())
    ranked = sorted((r for r in rows if r.entity_type in wanted and r.score >= MIN_SCORE
                     and not _keep(r.entity_type, text[r.start:r.end])),
                    key=lambda r: (-r.score, -(r.end - r.start), r.start))
    taken: list[Any] = []
    for row in ranked:
        if all(row.end <= other.start or row.start >= other.end for other in taken):
            taken.append(row)
    return sorted(taken, key=lambda r: r.start)


def scrub(text: str) -> Scrubbed:
    """`text` with its personal data replaced, and what was replaced. Raises `NotSent` when Presidio cannot run.

    The same value is the same placeholder through the text (`<PERSON_1>` ... `<PERSON_1>`); a kind with several different
    values numbers them, one value is just `<PERSON>`."""
    body = str(text or "")
    if not body.strip():
        return Scrubbed(body)
    engines = _engines()
    with _lock:                          # the analyzer is used by one message at a time: a message takes milliseconds
        rows = _chosen(body, _analyse(engines["analyzer"], body))
    if not rows:
        return Scrubbed(body)
    from presidio_anonymizer.entities import OperatorConfig

    values: dict[str, dict[str, int]] = {}
    for row in rows:
        values.setdefault(row.entity_type, {}).setdefault(body[row.start:row.end].strip().casefold(), len(values.get(row.entity_type, {})) + 1)

    def placeholder(entity: str):
        def make(value: str) -> str:
            number = values[entity].get(value.strip().casefold())          # Presidio also calls this once with a probe value
            return f"<{entity}_{number}>" if number and len(values[entity]) > 1 else f"<{entity}>"
        return make

    operators = {entity: OperatorConfig("custom", {"lambda": placeholder(entity)}) for entity in values}
    done = engines["anonymizer"].anonymize(text=body, analyzer_results=rows, operators=operators)
    found: dict[str, int] = {}
    for row in rows:
        found[row.entity_type] = found.get(row.entity_type, 0) + 1
    return Scrubbed(done.text, found)


def describe(found: dict[str, int]) -> str:
    """What was hidden, in words: `1 email address and 2 names`."""
    parts = []
    for entity, count in sorted(found.items(), key=lambda pair: (-pair[1], pair[0])):
        one, many = LABELS.get(entity, (entity.replace("_", " ").lower(),) * 2)
        parts.append(f"{count} {one if count == 1 else many}")
    return " and ".join([", ".join(parts[:-1]), parts[-1]] if len(parts) > 1 else parts)


def tell(project: str, found: dict[str, int]) -> None:
    """The line in the chat saying personal data was hidden."""
    if project and found:
        bus.agent_msg(project, f"Personal details were hidden before this went to the model: {describe(found)}. "
                               "It saw placeholders such as <EMAIL_ADDRESS> instead.", title="Privacy filter", kind="narration")


def screen(project: str, text: str) -> str:
    """The text to use in place of what the person typed: the same text, personal data replaced. Said in the chat when
    something was hidden. Raises `NotSent` when the filter is on and cannot run."""
    if not enabled():
        return str(text or "")
    done = scrub(text)
    tell(project, done.found)
    return done.text
