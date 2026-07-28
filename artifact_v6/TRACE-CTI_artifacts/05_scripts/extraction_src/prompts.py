"""Verbatim port of Zenodo gLLM/mitre.py prompts (sentence-level).
Source: gLLM/mitre.py:160-211 (create_mitre_sentence_based_rag_prompt).

Notes preserved (deliberate fidelity, documented in REPRODUCIBILITY_NOTES):
- The Zenodo prompt says "(Sub)Technique" only when is_bosch is None; since
  test_helper always passes True/False, the prompt always contains "Technique".
  We replicate this behavior here to match Table 9.
- 5 hardcoded few-shot examples + 1 negative example (6 total).
"""

SYSTEM_PROMPT = (
    "You are a Cyber Security Expert who finds MITRE ATT&CK framework concepts in CTI Reports."
)

CONSERVATIVE_INSTRUCTION = (
    "Only output a MITRE ATT&CK technique if the sentence itself provides explicit "
    "behavioral evidence for it. Do not output a technique merely because it appears "
    "in the candidate list. If the sentence is a title, heading, file path, table "
    "fragment, hash, registry value, numeric mapping, malware family name alone, or "
    "non-behavioral text, return No technique found. Prefer precision over recall. "
    "Return only techniques that are directly supported by the sentence."
)

# Replicated from mitre.py:200-205
HARDCODED_FSP_EXAMPLES = [
    ('TrickBot has used macros in Excel documents to download and deploy the malware on the user’s machine.',
     '- T1059: Command and Scripting Interpreter'),
    ('SombRAT has the ability to use an embedded SOCKS proxy in C2 communications.',
     '- T1090: Proxy'),
    ('Silent Librarian has exfiltrated entire mailboxes from compromised accounts.',
     '- T1114: Email Collection'),
    ('Azorult can collect a list of running processes by calling CreateToolhelp32Snapshot.',
     '- T1057: Process Discovery'),
    ('SeaDuke is capable of executing commands.',
     '- T1059: Command and Scripting Interpreter'),
    ('Figure 4 shows the architecture of Crutch v4.',
     'No technique found.'),
]


def build_sentence_rag_prompt(sentence, retrieved, few_shot=False, prompt_mode="zenodo"):
    if prompt_mode not in ("zenodo", "conservative"):
        raise ValueError(f"Unknown prompt_mode: {prompt_mode}")
    techniques_word = "Technique"  # see module docstring
    q = (
        f"List all MITRE ATT&CK {techniques_word} IDs and Names that occur in the sentence from a CTI report, "
        f"surrounded by grave accents (`). This sentence is a single sentence from a whole cyber threat report. "
        f"It is also possible that there is no MITRE ATT&CK {techniques_word} in this sentence. "
        f"The MITRE ATT&CK descriptions below (delimited by triple quotation marks (\"\"\") may or may not contain "
        f"MITRE ATT&CK {techniques_word} used in the sentence below.\n"
        "Do not give any assumptions, tips or similar! Please provide concise, non-repetitive answers.\n"
    )
    q += "MITRE ATT&CK Techniques:\n\"\"\"\n"
    for r in retrieved:
        q += "{\n"
        q += f"MITRE ATT&CK ID: {r['ID']}\n"
        q += f"MITRE ATT&CK Name: {r['name']}\n"
        q += f"MITRE ATT&CK Description: {r['description']}\n"
        q += "}\n"
    q += "\n\"\"\"\n"
    if few_shot:
        q += "A few examples for help (these examples are independent of the sentence to analyze).\n"
        for ex_sent, ex_resp in HARDCODED_FSP_EXAMPLES:
            q += f"For example: -Sentence: \"{ex_sent}\". Your Response: \"{ex_resp}\"\n"
    if prompt_mode == "conservative":
        q += f"\n{CONSERVATIVE_INSTRUCTION}\n"
    q += f"\nSentence to analyze: `{sentence}`\n"
    return q


def build_chat_messages(user_query):
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]
