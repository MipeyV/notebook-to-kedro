"""Preserved structured helper bodies with explicit linear orchestration."""


def clean_values(raw_values: list, missing_policy: str) -> list:
    """Drop or reject missing values according to the explicit policy."""
    cleaned = []
    for value in raw_values:
        if value is None:
            if missing_policy == "error":
                raise ValueError("Missing observation")
            continue
        cleaned.append(float(value))
    return cleaned


def winsorize(cleaned: list, lower: float, upper: float) -> list:
    """Clip observations without changing their order."""
    bounded = []
    for value in cleaned:
        if value < lower:
            bounded.append(lower)
        elif value > upper:
            bounded.append(upper)
        else:
            bounded.append(value)
    return bounded


def summarize(bounded: list) -> dict:
    """Summarize the retained values or raise the original empty-data error."""
    if not bounded:
        raise ValueError("No usable observations")
    return {
        "count": len(bounded),
        "mean": round(sum(bounded) / len(bounded), 8),
        "min": min(bounded),
        "max": max(bounded),
    }


def workflow(raw_values: list, missing_policy: str, lower: float, upper: float) -> dict:
    """Call each original helper once in the declared order."""
    cleaned = clean_values(raw_values, missing_policy)
    bounded = winsorize(cleaned, lower, upper)
    report = summarize(bounded)
    return report
