def merge_tag_filters(whitelist: str | None, blacklist: str | None) -> str | None:
    """Translate legacy excluded tags into the current search syntax."""
    terms = [term.strip() for term in (whitelist or "").split(",") if term.strip()]
    terms.extend(
        f"-#{term.strip()}" for term in (blacklist or "").split(",") if term.strip()
    )
    return ",".join(terms) or None
