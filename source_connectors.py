def load_manual_source_text(text):
    return {
        "source_type": "Manual text",
        "raw_text": text,
        "source_title": "",
        "source_url": "",
        "source_organization": "",
        "source_year": "",
    }


def load_pubmed_abstract(title, abstract, url=""):
    return {
        "source_type": "PubMed",
        "raw_text": title + "\n\n" + abstract,
        "source_title": title,
        "source_url": url,
        "source_organization": "PubMed",
        "source_year": "",
    }


def load_ema_text(title, text, url=""):
    return {
        "source_type": "EMA-HMPC",
        "raw_text": text,
        "source_title": title,
        "source_url": url,
        "source_organization": "EMA",
        "source_year": "",
    }


def load_who_text(title, text, url=""):
    return {
        "source_type": "WHO monograph",
        "raw_text": text,
        "source_title": title,
        "source_url": url,
        "source_organization": "WHO",
        "source_year": "",
    }


def load_escop_text(title, text, url=""):
    return {
        "source_type": "ESCOP monograph",
        "raw_text": text,
        "source_title": title,
        "source_url": url,
        "source_organization": "ESCOP",
        "source_year": "",
    }
