"""Lead scoring system for Empire Sales Agent.

Scores homeowners 0-100 based on renovation intent signals.
Higher score = more likely to need remodeling services.
"""

from datetime import datetime, date


def calculate_score(lead: dict, permits: list[dict] = None) -> tuple[int, list[str]]:
    """
    Calculate renovation intent score for a lead.

    Returns:
        tuple: (score 0-100, list of reason strings)
    """
    score = 0
    reasons = []
    permits = permits or []

    # --- Tier 1: Active permits (strongest signal) ---
    remodel_keywords = [
        "remodel", "renovation", "addition", "alteration", "interior",
        "kitchen", "bathroom", "flooring", "cabinet", "tile",
    ]
    for permit in permits:
        desc = (permit.get("description") or "").lower()
        ptype = (permit.get("permit_type") or "").lower()
        combined = f"{desc} {ptype}"
        if any(kw in combined for kw in remodel_keywords):
            score += 25
            reasons.append("Active remodeling permit found")
            break

    roof_keywords = ["roof", "re-roof", "reroof"]
    for permit in permits:
        desc = (permit.get("description") or "").lower()
        if any(kw in desc for kw in roof_keywords):
            score += 15
            reasons.append("Roofing permit (may need interior work too)")
            break

    # --- Tier 2: Recent purchase ---
    last_sale = lead.get("last_sale_date")
    if last_sale:
        if isinstance(last_sale, str):
            try:
                last_sale = datetime.strptime(last_sale, "%Y-%m-%d").date()
            except ValueError:
                last_sale = None

        if isinstance(last_sale, date):
            days_since_sale = (date.today() - last_sale).days
            if days_since_sale <= 365:
                score += 20
                reasons.append(f"Purchased {days_since_sale} days ago (new buyer)")
            elif days_since_sale <= 730:
                score += 10
                reasons.append("Purchased within last 2 years")

    # --- Tier 2: Below market value purchase ---
    sale_price = lead.get("last_sale_price")
    market_value = lead.get("market_value")
    if sale_price and market_value and market_value > 0:
        ratio = float(sale_price) / float(market_value)
        if ratio < 0.75:
            score += 15
            reasons.append(f"Bought at {ratio:.0%} of market value (fixer-upper)")
        elif ratio < 0.85:
            score += 8
            reasons.append(f"Bought below market value ({ratio:.0%})")

    # --- Tier 3: Age of home ---
    year_built = lead.get("year_built")
    if year_built:
        age = datetime.now().year - int(year_built)
        if age >= 30:
            score += 20
            reasons.append(f"Home is {age} years old (likely needs major updates)")
        elif age >= 20:
            score += 15
            reasons.append(f"Home is {age} years old (aging systems)")
        elif age >= 15:
            score += 8
            reasons.append(f"Home is {age} years old")

    # --- Tier 3: No homestead (investor property) ---
    if lead.get("homestead") is False:
        score += 10
        reasons.append("No homestead exemption (likely investor)")

    # --- Tier 3: High assessed value (can afford renovation) ---
    assessed = lead.get("assessed_value")
    if assessed:
        assessed = float(assessed)
        if assessed >= 500000:
            score += 10
            reasons.append(f"High-value property (${assessed:,.0f})")
        elif assessed >= 300000:
            score += 5
            reasons.append(f"Mid-high value property (${assessed:,.0f})")

    # --- Tier 3: Long ownership + no permits ---
    if last_sale and isinstance(last_sale, date):
        years_owned = (date.today() - last_sale).days / 365
        if years_owned >= 15 and len(permits) == 0:
            score += 10
            reasons.append(f"Owned {years_owned:.0f} years with no permits")

    # --- Negative signals ---
    if lead.get("do_not_call"):
        score -= 50
        reasons.append("NEGATIVE: On do-not-call list")

    # Clamp to 0-100
    score = max(0, min(100, score))

    return score, reasons
