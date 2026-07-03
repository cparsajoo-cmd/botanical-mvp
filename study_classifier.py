import re

STUDY_PATTERNS = {

    "Meta-analysis": [
        r"\bmeta[- ]analysis\b",
        r"\bmeta analysis\b"
    ],

    "Systematic review": [
        r"\bsystematic review\b"
    ],

    "Randomized Controlled Trial": [
        r"\brandomized\b",
        r"\brandomised\b",
        r"\bdouble blind\b",
        r"\bplacebo controlled\b",
        r"\brct\b"
    ],

    "Clinical Trial": [
        r"\bclinical trial\b",
        r"\bpilot study\b",
        r"\bpatients\b",
        r"\bhealthy volunteers\b"
    ],

    "Observational": [
        r"\bcohort\b",
        r"\bcase control\b",
        r"\bcross sectional\b",
        r"\bobservational\b"
    ],

    "Case Report": [
        r"\bcase report\b",
        r"\bcase series\b"
    ],

    "Animal": [
        r"\brat\b",
        r"\brats\b",
        r"\bmouse\b",
        r"\bmice\b",
        r"\brabbit\b",
        r"\bdog\b",
        r"\banimal model\b"
    ],

    "In vitro": [
        r"\bin vitro\b",
        r"\bcell line\b",
        r"\bcell culture\b"
    ],

    "Review": [
        r"\breview\b"
    ]

}


def classify_study(text):

    text = text.lower()

    for study, patterns in STUDY_PATTERNS.items():

        for p in patterns:

            if re.search(p, text):

                return study

    return "Unknown"
