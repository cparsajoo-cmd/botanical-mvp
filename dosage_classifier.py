import re


DOSAGE_PATTERNS = {
    "Infusion": [
        r"\binfusion\b",
        r"\bherbal tea\b",
        r"\btea\b",
        r"\btisane\b",
    ],
    "Decoction": [
        r"\bdecoction\b",
    ],
    "Capsule": [
        r"\bcapsule\b",
        r"\bcapsules\b",
    ],
    "Tablet": [
        r"\btablet\b",
        r"\btablets\b",
    ],
    "Extract": [
        r"\bextract\b",
        r"\bdry extract\b",
        r"\bstandardized extract\b",
        r"\bstandardised extract\b",
        r"\bhydroalcoholic extract\b",
        r"\bethanolic extract\b",
        r"\baqueous extract\b",
    ],
    "Essential oil": [
        r"\bessential oil\b",
        r"\bvolatile oil\b",
        r"\baromatherapy\b",
    ],
    "Tincture": [
        r"\btincture\b",
    ],
    "Syrup": [
        r"\bsyrup\b",
    ],
    "Cream": [
        r"\bcream\b",
    ],
    "Gel": [
        r"\bgel\b",
    ],
    "Ointment": [
        r"\boinment\b",
        r"\bointment\b",
    ],
    "Lotion": [
        r"\blotion\b",
    ],
    "Spray": [
        r"\bspray\b",
        r"\bnasal spray\b",
    ],
    "Mouthwash": [
        r"\bmouthwash\b",
        r"\bgargle\b",
        r"\boral rinse\b",
    ],
    "Drops": [
        r"\bdrops\b",
        r"\boral drops\b",
        r"\beye drops\b",
    ],
    "Powder": [
        r"\bpowder\b",
        r"\bpowders\b",
    ],
    "Softgel": [
        r"\bsoftgel\b",
        r"\bsoft gel\b",
    ],
    "Patch": [
        r"\bpatch\b",
        r"\btransdermal patch\b",
    ],
    "Suppository": [
        r"\bsuppository\b",
        r"\bsuppositories\b",
    ],
}


def detect_dosage_forms(text):
    text = str(text or "").lower()
    detected = []

    for dosage_form, patterns in DOSAGE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                detected.append(dosage_form)
                break

    return detected


def classify_dosage_form(text):
    detected = detect_dosage_forms(text)

    if not detected:
        return "Unknown"

    return detected[0]


def dosage_form_relevance(selected_dosage_form, detected_dosage_forms):
    selected = str(selected_dosage_form or "").strip().lower()
    detected = [str(x).strip().lower() for x in detected_dosage_forms]

    if not selected:
        return "Unknown"

    if selected in detected:
        return "Direct"

    if detected:
        return "Indirect"

    return "Unknown"
