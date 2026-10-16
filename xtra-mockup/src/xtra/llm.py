"""The language model, behind a replaceable boundary (specification section 5.3).

The rest of the system hands over a task, a sentence and the relevant CTDL definitions, and
receives a proposal: a structure, an exact quote for each part, and a short argument. Nothing in
a proposal is trusted until the guards in `prereq` pass.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

PROMPT_VERSION = "prerequisite-structure/1"

SYSTEM_PROMPT = """You read one requirement sentence from a university course catalog and write its logical structure as a tree.

A node has a "kind":
- "all_of": every item under it is required. Written with "and", or a comma list that ends in "and".
- "any_of": one item under it is enough. Written with "or".
- "course": one course code. Its "quote" is the code exactly as written, for example "MATH 20503".
- "text": any condition that is not a course code: a grade, a class standing, a group of students, consent, a test score. Its "quote" is the exact words.

Rules:
1. Copy every quote character for character from the sentence. Never paraphrase.
2. Use every course code in the sentence, once for each time it appears, in the order it appears. Never add a course code that is not in the sentence.
3. Keep the parts in the order they appear in the sentence.
4. Brackets group. Courses joined by "and" inside brackets are one "all_of". Courses joined by "or" inside brackets are one "any_of".
5. "all_of" and "any_of" nodes have "items" and an empty "quote". "course" and "text" nodes have a "quote" and no items.

Also write "argument": two sentences saying how you read the "and" and "or" in this sentence, citing the CTDL definitions you are given."""


@dataclass(frozen=True)
class Proposal:
    structure: object  # nested dicts: kind / quote / items
    argument: str
    model: str
    prompt_version: str
    seconds: float | None = None
    cached: bool = False


class Proposer(Protocol):
    name: str

    def propose(self, task: str, sentence: str, course_codes: list[str], definitions: dict[str, str]) -> Proposal | None: ...


def _node_schema(depth: int) -> dict:
    node: dict = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["all_of", "any_of", "course", "text"] if depth > 0 else ["course", "text"]},
            "quote": {"type": "string"},
        },
        "required": ["kind", "quote"],
    }
    if depth > 0:
        node["properties"]["items"] = {"type": "array", "items": _node_schema(depth - 1)}
    return node


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"structure": _node_schema(4), "argument": {"type": "string"}},
    "required": ["structure", "argument"],
}


def user_prompt(task: str, sentence: str, course_codes: list[str], definitions: dict[str, str]) -> str:
    lines = ["CTDL definitions:"]
    lines += [f"- {term}: \"{text}\"" for term, text in definitions.items()]
    lines.append("")
    lines.append(f"This sentence is a {task}.")
    lines.append("Course codes in the sentence, in order: " + (", ".join(course_codes) if course_codes else "(none)"))
    lines.append("Sentence:")
    lines.append(sentence)
    return "\n".join(lines)


class OllamaProposer:
    """A language model served by ollama on this machine. Answers are cached by model name,
    prompt version and input, so extraction is repeatable (EX2)."""

    def __init__(self, model: str, cache_dir: Path, host: str = "http://localhost:11434", timeout: float = 300.0):
        self.name = model
        self.model = model
        self.cache_dir = Path(cache_dir) / model.replace(":", "_").replace("/", "_")
        self.host = host
        self.timeout = timeout
        self.calls = 0
        self.cache_hits = 0
        self.errors: list[str] = []

    def _key(self, task: str, sentence: str, course_codes: list[str], definitions: dict[str, str]) -> str:
        material = json.dumps([self.model, PROMPT_VERSION, task, sentence, course_codes, definitions], ensure_ascii=False)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def propose(self, task, sentence, course_codes, definitions):
        key = self._key(task, sentence, course_codes, definitions)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            self.cache_hits += 1
            saved = json.loads(path.read_text(encoding="utf-8"))
            return Proposal(saved["structure"], saved["argument"], self.model, PROMPT_VERSION, saved.get("seconds"), cached=True)
        body = {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": RESPONSE_SCHEMA,
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 900},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt(task, sentence, course_codes, definitions)},
            ],
        }
        import time

        started = time.monotonic()
        try:
            request = urllib.request.Request(
                self.host + "/api/chat", data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                answer = json.load(response)
            content = json.loads(answer["message"]["content"])
            structure, argument = content["structure"], str(content.get("argument", ""))
        except Exception as error:  # the model being absent or confused must never stop a run
            self.errors.append(f"{type(error).__name__}: {error}")
            return None
        seconds = round(time.monotonic() - started, 1)
        self.calls += 1
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "model": self.model,
                    "promptVersion": PROMPT_VERSION,
                    "task": task,
                    "sentence": sentence,
                    "courseCodes": course_codes,
                    "structure": structure,
                    "argument": argument,
                    "seconds": seconds,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return Proposal(structure, argument, self.model, PROMPT_VERSION, seconds)


class NonsenseProposer:
    """A stand-in that returns rubbish, to prove the guards hold (acceptance criterion)."""

    name = "nonsense (stand-in)"

    def propose(self, task, sentence, course_codes, definitions):
        return Proposal(
            {
                "kind": "any_of",
                "quote": "",
                "items": [
                    {"kind": "course", "quote": "FAKE 99999"},
                    {"kind": "text", "quote": "colourless green ideas sleep furiously"},
                    *({"kind": "course", "quote": code} for code in reversed(course_codes)),
                ],
            },
            "Nonsense, on purpose.",
            self.name,
            PROMPT_VERSION,
        )


class NoProposer:
    name = "none"

    def propose(self, task, sentence, course_codes, definitions):
        return None


def make_proposer(spec: str, cache_dir: Path) -> Proposer:
    if spec == "none":
        return NoProposer()
    if spec == "nonsense":
        return NonsenseProposer()
    if spec.startswith("ollama:"):
        return OllamaProposer(spec[len("ollama:") :], cache_dir)
    raise SystemExit(f'unknown language model "{spec}"; use "ollama:<name>", "nonsense" or "none"')
