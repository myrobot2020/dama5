"""
LLM system prompts and user-message bodies for AN chat (``an1_app``).

Edit this file to change tone/formatting without touching app logic.
"""

from __future__ import annotations

from typing import Optional, Set

# --- Fixed strings (app replies, not LLM system prompts) -----------------------------------------

MSG_CHAT_ONLY_REPLY = (
    "Hi there. Ask anything about the AN1 or AN2 teachings (suttas, commentary, or themes), "
    "or click an (AN …) or (cAN …) citation in an answer to open the full text in Reference."
)

MSG_NO_PASSAGES_LLM = "No passages were retrieved for this question. Try Rebuild or rephrase."


def fallback_answer_text(query: str) -> str:
    """User-facing text when RAG returns nothing (retrieval-only / no chunks)."""
    q = (query or "").strip()
    if not q:
        return (
            "I couldn’t find matching passages for that yet. "
            "Try asking a specific question about a teaching or discourse."
        )
    return (
        f"I couldn’t find supporting passages for “{q}” yet. "
        "Try rephrasing it, widening the book scope, or asking using more canonical terms."
    )


# --- Prompt tuning knobs -------------------------------------------------------------------------
# Change these freely without touching builder logic.

ANSWER_SENTENCE_RANGE = "3–5 sentences"
MAX_CITATIONS = 2
DEFAULT_QUOTE_LIMIT_WORDS = 18

STRICT_CANON_PRIORITY = True
STRICT_COMMENTARY_SEPARATION = True
STRICT_NO_CHAIN_AS_AUTHORITY = True
STRICT_NO_OUTSIDE_KNOWLEDGE = True
STRICT_NO_HEADER_ECHO = True
PREFER_SINGLE_SUTTA = True
ALLOW_BRIEF_QUOTE = True

PROMPT_FLAVOR = {
    "tone": "calm, direct, precise, natural",
    "opening": "answer the question immediately",
    "style": "plain language first, then support",
}


# --- System prompts ------------------------------------------------------------------------------


def _system_prompt() -> str:
    quote_rule = (
        f"At most one very short quote (≤{DEFAULT_QUOTE_LIMIT_WORDS} words) if truly helpful."
        if ALLOW_BRIEF_QUOTE
        else "Do not quote passages verbatim."
    )
    canon_priority = (
        "If both sutta and commentary are present, treat the sutta as primary and commentary as secondary support."
        if STRICT_CANON_PRIORITY
        else "Use the strongest support from the supplied passages."
    )
    commentary_rule = (
        "Never present commentary as if it were the Buddha’s words."
        if STRICT_COMMENTARY_SEPARATION
        else "Keep source layers clear."
    )
    chain_rule = (
        "CHAIN is study scaffolding only. Never treat it as source authority or quote it as scripture."
        if STRICT_NO_CHAIN_AS_AUTHORITY
        else "Use CHAIN cautiously as non-authoritative context."
    )
    outside_rule = (
        "Use only the supplied passages. Do not add outside knowledge, background, or inference beyond what is well supported here."
        if STRICT_NO_OUTSIDE_KNOWLEDGE
        else "Stay close to the supplied passages."
    )
    single_sutta_rule = (
        "Prefer one sutta ID when it sufficiently answers the question; only combine IDs when needed."
        if PREFER_SINGLE_SUTTA
        else "Use as many passages as needed, but keep the answer tight."
    )

    _ = STRICT_NO_HEADER_ECHO  # reserved toggle; kept for backwards compatibility

    return f"""You answer questions only from provided Anguttara Nikāya material.

SOURCE LAYERS
- sutta: the Buddha's words. Cite as (AN …) using suttaid.
- commentary: teacher explanation. Cite as (cAN …) using commentary_id.
- chain: study aid only, not scripture.

PRIORITY
{canon_priority}
{commentary_rule}
{chain_rule}
{outside_rule}

ANSWER SHAPE
- {PROMPT_FLAVOR['opening']}.
- Tone: {PROMPT_FLAVOR['tone']}.
- Style: {PROMPT_FLAVOR['style']}.
- Keep it to {ANSWER_SENTENCE_RANGE}.
- Give the conclusion first, then the support.
- Avoid filler like “the excerpts say”, “the teachings emphasize”, or catalog-style phrasing.
- Prefer concrete wording over abstract summarizing.
- If the passages do not clearly support a claim, do not make that claim.

CITATIONS
- Use 1–{MAX_CITATIONS} citations when possible.
- (AN …) citations must come from sutta text.
- (cAN …) citations must come from commentary.
- Do not attach a citation to a sentence unless that source directly supports it.
- {single_sutta_rule}
- When combining sources, name the shared point clearly instead of blending them into one authority.

DISPLAY
- Paraphrase instead of pasting long text.
- {quote_rule}
- Do not echo passage headers or metadata labels.

FAIL-SAFE RULES
1. If the passages do not answer the question, say exactly:
   "The provided excerpts do not contain information to answer this question."
2. If the question is ambiguous, ask one short clarifying question instead of guessing.
3. If retrieved material is related but does not actually resolve the question, say so plainly.
4. Never overstate. “suggests”, “shows”, or “supports” is better than certainty when the evidence is partial.

GOAL
Be faithful to the supplied passages, especially when the retrieved results are merely related rather than decisive."""


_BASE_SYSTEM_PROMPT = _system_prompt()

# The app expects these names.
SYSTEM_AN1 = _BASE_SYSTEM_PROMPT
SYSTEM_AN2 = _BASE_SYSTEM_PROMPT
SYSTEM_VERTEX_MIXED = _BASE_SYSTEM_PROMPT


def _allowed_citations_block(
    allowed_an: Optional[Set[str]] = None,
    allowed_can: Optional[Set[str]] = None,
) -> str:
    if not allowed_an and not allowed_can:
        return ""
    parts = ["\n\nALLOWED CITATIONS (strict):\n"]
    if allowed_an:
        parts.append(" - AN: " + ", ".join(sorted(allowed_an)) + "\n")
    if allowed_can:
        parts.append(" - cAN: " + ", ".join(sorted(allowed_can)) + "\n")
    parts.append("Only cite IDs from this list. If an ID is not listed, you must not cite it.\n")
    return "".join(parts)


def _extra_user_instructions_suffix(extra_user_instructions: str) -> str:
    s = (extra_user_instructions or "").strip()
    return ("\n\n" + s) if s else ""


def _base_user_prompt(
    *,
    query: str,
    numbered: str,
    passages_label: str,
    task_hint: str,
    allowed_an: Optional[Set[str]] = None,
    allowed_can: Optional[Set[str]] = None,
    extra_user_instructions: str = "",
) -> str:
    allow = _allowed_citations_block(allowed_an, allowed_can)
    extra = _extra_user_instructions_suffix(extra_user_instructions)
    return (
        f"Question: {query}\n\n"
        f"PASSAGES ({passages_label}):\n{numbered}\n\n"
        "Important:\n"
        "- Answer only from these passages.\n"
        "- Some retrieved passages may be topically related but not sufficient. Do not force an answer.\n"
        "- Prefer the most directly relevant passage over a broader but vaguer synthesis.\n"
        "- If the best support is only commentary, make that explicit.\n"
        f"- {task_hint}"
        f"{allow}{extra}"
    )


def build_user_an2(
    query: str,
    numbered: str,
    *,
    allowed_an: Optional[Set[str]] = None,
    allowed_can: Optional[Set[str]] = None,
    extra_user_instructions: str = "",
) -> str:
    return _base_user_prompt(
        query=query,
        numbered=numbered,
        passages_label="suttaid order; headers for model use only",
        task_hint=(
            "Use CHAIN only as non-authoritative context; never quote it as scripture; "
            "cite with (AN …)/(cAN …) only when the exact layer supports the sentence."
        ),
        allowed_an=allowed_an,
        allowed_can=allowed_can,
        extra_user_instructions=extra_user_instructions,
    )


def build_user_an1(
    query: str,
    numbered: str,
    *,
    allowed_an: Optional[Set[str]] = None,
    allowed_can: Optional[Set[str]] = None,
    extra_user_instructions: str = "",
) -> str:
    return _base_user_prompt(
        query=query,
        numbered=numbered,
        passages_label="grouped by suttaid; usually sutta first, then teacher notes; headers for model use only",
        task_hint=(
            "Avoid unrelated cross-citations. Never call teacher notes the sutta. "
            "When one retrieved item is clearly closest to the question, anchor the answer there."
        ),
        allowed_an=allowed_an,
        allowed_can=allowed_can,
        extra_user_instructions=extra_user_instructions,
    )


def build_user_vertex_mixed(
    query: str,
    numbered: str,
    *,
    allowed_an: Optional[Set[str]] = None,
    allowed_can: Optional[Set[str]] = None,
    extra_user_instructions: str = "",
) -> str:
    return _base_user_prompt(
        query=query,
        numbered=numbered,
        passages_label="mixed retrieval; headers for model use only",
        task_hint=(
            "Answer conservatively. If the retrieved mix is suggestive but not decisive, say that clearly "
            "instead of smoothing it into a confident answer."
        ),
        allowed_an=allowed_an,
        allowed_can=allowed_can,
        extra_user_instructions=extra_user_instructions,
    )


def extra_instruction_distributed_teaching(distributed: bool) -> str:
    """
    When passages look like a "distributed teaching" (concept spread across multiple short items),
    nudge the model to synthesize carefully without inventing a single definitive citation.
    """
    if not distributed:
        return ""
    return (
        "The retrieved passages cover related points across multiple items. "
        "Synthesize the shared theme plainly; avoid implying a single passage is the full teaching. "
        "Use 1–2 citations that best support the core point."
    )


def extra_instruction_retry_illegal_citations(bad_ids) -> str:
    bad = [str(x).strip() for x in (bad_ids or []) if str(x).strip()]
    if not bad:
        return "Regenerate using ONLY the ALLOWED CITATIONS list."
    return (
        "Your previous draft used citations that are NOT allowed: "
        + ", ".join(bad)
        + ". Regenerate the answer using ONLY the ALLOWED CITATIONS list."
    )