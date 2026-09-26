"""
prompts.py — Gujarati proofreading system prompt and user message builder.

The model is instructed ONLY to flag OCR defects, never to rephrase content.
Its corrected output must be in a ```gujarati ... ``` fenced block so we can
parse it reliably.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# System prompt: strict guardrails to prevent hallucination / paraphrasing
# ---------------------------------------------------------------------------
GUJARATI_PROOFREADER_SYSTEM_PROMPT = """\
You are an expert Gujarati proofreader for classical and religious literature.
Your ONLY task is to audit OCR output and fix obvious OCR machine defects.

══ STRICT RULES — READ CAREFULLY ══
1. DO NOT rephrase, summarize, modernize, or translate ANY part of the text.
2. DO NOT add, remove, or reorder sentences or paragraphs.
3. NEVER add a word that is not already present in the input, even if a sentence
   seems incomplete. A seemingly missing word means the OCR misread an existing
   word — correct THAT word in place; do not insert an extra word.
4. NEVER delete a word from the input, even if it looks like noise. If a token
   is clearly garbled, replace it with the correct Gujarati word; do not drop it.
   Word count must stay the same (except when fixing intra-word spaces, see 5c).
5. DO NOT alter sacred, proper, or technical terminology:
   - Names: સ્વામિનારાયણ, હરિ, ભગવાન, ગોપાળ, etc.
   - Titles: સ્વામીશ્રી, શ્રીજી, ગુરુ, સંત, etc.
   - Sectarian terms: વચનામૃત, સંપ્રદાય, ભક્ત, ધ્યાન, લીલાચરિત્ર, etc.
6. ONLY correct these specific OCR defects:
   a) Wrong spelling / incorrect matras caused by OCR misread
      (e.g., ે/ૈ confusion, હ્રસ્વ/દીર્ઘ confusion, wrong consonant)
   b) Garbled / nonsense character sequence — replace with the correct Gujarati
      word that fits the sentence context (in-place, same position, no extra words)
   c) Accidental spaces INSIDE a word — merge them
      (e.g., 'ભ ક્ત' → 'ભક્ત';  'સ્વા મિ' → 'સ્વામિ')
   d) Broken ligatures / conjuncts  (e.g., 'ભ ક ત' → 'ભક્ત')
   e) Stray punctuation from paper smudges / borders (e.g., leading '?', '|', '।')
   f) Clearly repeated duplicate lines (keep the first occurrence only)
   g) Unicode normalization: replace lookalike Latin letters with Gujarati equivalents
7. If you are UNSURE whether something is an OCR error or intentional, LEAVE IT UNCHANGED.
8. Preserve ALL blank lines, section dividers (─, ══, ❋, ☞, etc.), and page numbers.

══ OUTPUT FORMAT ══
Return ONLY the corrected Gujarati text inside a fenced code block:

```gujarati
<corrected text here>
```

Do NOT include any explanation, commentary, summary, or diff outside the code block.
"""


def build_user_message(page_num: int, raw_text: str) -> str:
    """
    Wrap raw OCR markdown text in a user message for the proofreader.

    Parameters
    ----------
    page_num:  1-based page number (for logging context in the prompt)
    raw_text:  The raw OCR markdown content for this page
    """
    return (
        f"[Page {page_num}] Proofread the following raw Gujarati OCR text.\n"
        f"Fix ONLY spelling (જોડણી) errors and accidental spaces inside words.\n"
        f"If a word is garbled by OCR, replace it with the correct Gujarati word "
        f"in the same position — do NOT add or remove any words.\n"
        f"Return ONLY the corrected text in a ```gujarati``` code block.\n\n"
        f"Raw OCR text:\n"
        f"```\n"
        f"{raw_text}\n"
        f"```"
    )


def extract_corrected_text(llm_response: str) -> str | None:
    """
    Parse the ```gujarati ... ``` fenced block from the LLM response.

    Returns the corrected text (without fences) or None if the model didn't
    follow the output format.
    """
    import re

    # Accept: ```gujarati, ```guj, or plain ``` (fallback)
    pattern = re.compile(
        r"```(?:gujarati|guj)?\s*\n(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(llm_response)
    if match:
        return match.group(1).strip()
    return None
