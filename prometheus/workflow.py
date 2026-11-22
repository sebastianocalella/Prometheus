"""Conversation stages and compact, per-session project memory."""
from dataclasses import dataclass, field
import json


STAGES = ("brainstorming", "consulting", "documentation")


@dataclass
class ProjectMemory:
    idea: str = ""
    confirmed_decisions: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    proposed_options: list[str] = field(default_factory=list)


@dataclass
class DocumentDraft:
    name: str
    overview: str
    concept_map: str
    next_steps: str
    context: str


@dataclass
class WorkflowState:
    stage: str = "brainstorming"
    memory: ProjectMemory = field(default_factory=ProjectMemory)
    draft: DocumentDraft | None = None
    saved_directory: str = ""


BASE_INSTRUCTIONS = """You are Prometheus, a concise English-language project-shaping partner.
The user's first message is the project description; start immediately. Answer direct questions.
Ask at most one short, targeted question per turn, and never repeat an answered question.
Do not force a checklist or a number of turns. A complete initial idea can skip brainstorming.
Distinguish proposals from decisions. Record only decisions the user explicitly confirmed.
You may move between brainstorming and consulting whenever a crucial gap or confusion appears.
Move to documentation only when the main decisions and a useful range of approaches/tools are settled.
Do not claim to have saved files. The application handles saving after explicit approval.
If documents were already saved, prepare revised drafts when decisions change; the application
will update them after another explicit confirmation.

Return ONLY one JSON object with these fields:
"message": brief user-facing reply;
"stage": one of brainstorming, consulting, documentation, describing the approach for the NEXT turn;
"memory": object with idea (string), confirmed_decisions (string list), open_questions (string list), proposed_options (string list);
"draft": null, or an object with name, overview, concept_map, next_steps, context (all strings).
Preserve relevant prior memory. Remove an open question once answered. Never invent confirmation.
Only provide a draft when stage is documentation and confirmed decisions exist. If drafting, show the
essential decisions in message and ask the user to confirm saving them. Keep all documents concise.
"""


STAGE_INSTRUCTIONS = {
    "brainstorming": "Clarify the most important missing cardinal point with a brief question. If already clear, switch to consulting or documentation.",
    "consulting": "Suggest the most useful approach, method, material or tool with essential tradeoffs. Ask for confirmation of a key choice. Return to brainstorming if an essential point becomes unclear.",
    "documentation": "Summarize settled decisions and prepare or revise compact documentation. Return to consulting or brainstorming if the user reopens a key choice.",
}


def system_prompt(state: WorkflowState) -> str:
    memory = json.dumps(state.memory.__dict__, ensure_ascii=False)
    saved = "yes" if state.saved_directory else "no"
    return f"{BASE_INSTRUCTIONS}\nCurrent stage: {state.stage}. {STAGE_INSTRUCTIONS[state.stage]}\nDocuments already saved: {saved}.\nCurrent memory: {memory}"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("Invalid memory list")
    return [item.strip() for item in value if item.strip()]


def apply_response(state: WorkflowState, raw: str) -> str:
    """Validate a model proposal before committing its stage or memory."""
    try:
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Expected object")
        message, stage, memory = result["message"], result["stage"], result["memory"]
        if not isinstance(message, str) or not message.strip() or stage not in STAGES or not isinstance(memory, dict):
            raise ValueError("Invalid workflow response")
        idea = memory["idea"]
        if not isinstance(idea, str) or not idea.strip():
            raise ValueError("Missing idea")
        next_memory = ProjectMemory(
            idea=idea.strip(),
            confirmed_decisions=_string_list(memory["confirmed_decisions"]),
            open_questions=_string_list(memory["open_questions"]),
            proposed_options=_string_list(memory["proposed_options"]),
        )
        if stage == "documentation" and not next_memory.confirmed_decisions:
            raise ValueError("Documentation requires confirmed decisions")
        draft_data = result.get("draft")
        draft = None
        if draft_data is not None:
            if stage != "documentation" or not isinstance(draft_data, dict):
                raise ValueError("Unexpected draft")
            values = [draft_data[key] for key in ("name", "overview", "concept_map", "next_steps", "context")]
            if not all(isinstance(value, str) and value.strip() for value in values):
                raise ValueError("Incomplete draft")
            draft = DocumentDraft(*(value.strip() for value in values))
        state.stage = stage
        state.memory = next_memory
        state.draft = draft
        return message.strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("The AI returned an invalid workflow response. Please retry.") from exc


def is_save_confirmation(text: str) -> bool:
    """Recognize an unambiguous response to the pending save question."""
    return text.strip().lower().rstrip(".! ") in {"yes", "yes, save it", "save it", "save", "confirm", "confirmed"}
