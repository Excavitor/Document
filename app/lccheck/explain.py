"""AI explanations for LC check findings using the local model.

The AI only explains differences that Python has already identified. It never
decides whether a discrepancy should be accepted or rejected. Any quotes
produced by the model are verified against source values.
"""
import re
from chat.llm_client import ModelError, ask_model

SYSTEM_PROMPT = (
    "You are a trade finance document checking assistant. "
    "You explain discrepancies between a Letter of Credit (LC) and an invoice in 1 or 2 plain, concise sentences. "
    "Rules:\n"
    "1. Rely strictly on the given values and evidence.\n"
    "2. Do not invent any facts, numbers, dates, or trade rules.\n"
    "3. Keep the tone factual, neutral, and clear."
)


def verify_quoted_evidence(explanation, context_texts):
    """Checks whether any quotation marks ("..." or '...') in explanation exist in the context.

    Returns (is_valid, unverified_quotes).
    """
    quotes = re.findall(r'["\u201c\u201d]([^"\u201c\u201d]{3,})["\u201c\u201d]', explanation)
    if not quotes:
        return True, []

    combined_context = " ".join(t.lower() for t in context_texts if t)
    unverified = []
    for q in quotes:
        clean_q = " ".join(q.strip().lower().split())
        if clean_q not in combined_context:
            unverified.append(q)
    return len(unverified) == 0, unverified


def generate_explanation(field_info):
    """Generate a 1-2 sentence explanation for a flagged row.

    field_info dict contains:
      - field: field key (e.g. 'goods_description')
      - label: human label (e.g. 'Goods')
      - status: 'MISMATCH', 'MISSING', 'NEEDS_REVIEW', etc.
      - lc_tag: SWIFT tag (e.g. '45A')
      - lc_value: what the LC specifies
      - doc_value: what the invoice specifies
      - evidence: line provenance from invoice
      - note: note from Python comparison
    """
    label = field_info.get("label") or field_info.get("field") or "Field"
    status = field_info.get("status") or "FLAGGED"
    tag = field_info.get("lc_tag") or ""
    lc_val = field_info.get("lc_value") or "Not specified in LC"
    doc_val = field_info.get("doc_value") or "Missing / Not shown"
    evidence = field_info.get("evidence") or ""
    note = field_info.get("note") or ""

    user_prompt = (
        f"Field: {label} (SWIFT Tag {tag})\n"
        f"Status: {status}\n"
        f"LC Requirement: {lc_val}\n"
        f"Invoice Shows: {doc_val}\n"
    )
    if evidence:
        user_prompt += f"Invoice Evidence Line: {evidence}\n"
    if note:
        user_prompt += f"Comparison Rule Note: {note}\n"

    user_prompt += (
        "\nIn 1 or 2 clear sentences, explain why this was flagged and how the invoice differs from the LC. /no_think"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        res = ask_model(messages, temperature=0.1, max_tokens=150)
        text = res["reply"].strip()
        # Verify any quoted strings in the explanation
        contexts = [lc_val, doc_val, evidence, note]
        quotes_valid, unverified = verify_quoted_evidence(text, contexts)
        return {
            "explanation": text,
            "seconds": res["seconds"],
            "quotes_valid": quotes_valid,
            "unverified_quotes": unverified,
            "error": None,
        }
    except ModelError as exc:
        return {
            "explanation": None,
            "seconds": None,
            "quotes_valid": True,
            "unverified_quotes": [],
            "error": str(exc),
        }
