"""Geographic Classification and Location Scoring for CareerOrbit AI.
Implements India-First Geographic Priorities and Location Eligibility.

Priority 1 (Highest):
  - Bengaluru, Chennai, Coimbatore, Hyderabad
  - Confirmed India-remote opportunities (explicitly India-available or worldwide)
  - Other South Indian locations: Cuddalore, Puducherry, Kochi, Mysuru, Madurai, Salem, Trichy, etc.

Priority 2 (Other Indian Locations):
  - Pune, Mumbai, Delhi NCR, Noida, Gurugram, Ahmedabad, Kolkata, and other Indian technology hubs.

Priority 3 (International / Location-Ambiguous):
  - International opportunities with explicit candidate eligibility or confirmed India remote permission.
  - Location-ambiguous remote postings: marked LOCATION_ELIGIBILITY_UNCONFIRMED (0 score, unranked above India-eligible).
"""
import re
from typing import Any, Dict, Optional, Tuple

# Geographic Priority Labels
GEO_PRIORITY_LABELS = {
    1: "Priority 1 — South India Metros & India Remote",
    2: "Priority 2 — South India Regional & Home Hubs",
    3: "Priority 3 — Other Indian Tech Hubs",
    4: "Priority 4 — International / Location Unconfirmed",
}

# South Indian Major Cities (Priority 1)
P1_PRIMARY_CITIES = {
    "bengaluru": ("Bengaluru", "Karnataka"),
    "bangalore": ("Bengaluru", "Karnataka"),
    "chennai": ("Chennai", "Tamil Nadu"),
    "madras": ("Chennai", "Tamil Nadu"),
    "coimbatore": ("Coimbatore", "Tamil Nadu"),
    "hyderabad": ("Hyderabad", "Telangana"),
    "secunderabad": ("Hyderabad", "Telangana"),
}

P1_OTHER_SOUTH_CITIES = {
    "cuddalore": ("Cuddalore", "Tamil Nadu"),
    "puducherry": ("Puducherry", "Puducherry"),
    "pondicherry": ("Puducherry", "Puducherry"),
    "kochi": ("Kochi", "Kerala"),
    "cochin": ("Kochi", "Kerala"),
    "mysuru": ("Mysuru", "Karnataka"),
    "mysore": ("Mysuru", "Karnataka"),
    "thiruvananthapuram": ("Thiruvananthapuram", "Kerala"),
    "trivandrum": ("Thiruvananthapuram", "Kerala"),
    "madurai": ("Madurai", "Tamil Nadu"),
    "salem": ("Salem", "Tamil Nadu"),
    "tiruchirappalli": ("Tiruchirappalli", "Tamil Nadu"),
    "trichy": ("Tiruchirappalli", "Tamil Nadu"),
    "tirunelveli": ("Tirunelveli", "Tamil Nadu"),
    "vellore": ("Vellore", "Tamil Nadu"),
    "erode": ("Erode", "Tamil Nadu"),
    "visakhapatnam": ("Visakhapatnam", "Andhra Pradesh"),
    "vizag": ("Visakhapatnam", "Andhra Pradesh"),
    "vijayawada": ("Vijayawada", "Andhra Pradesh"),
    "mangaluru": ("Mangaluru", "Karnataka"),
    "mangalore": ("Mangaluru", "Karnataka"),
    "hubli": ("Hubli", "Karnataka"),
    "dharwad": ("Dharwad", "Karnataka"),
    "calicut": ("Kozhikode", "Kerala"),
    "kozhikode": ("Kozhikode", "Kerala"),
    "thrissur": ("Thrissur", "Kerala"),
}

# Other Indian Tech Hubs (Priority 2)
P2_INDIAN_CITIES = {
    "pune": ("Pune", "Maharashtra"),
    "mumbai": ("Mumbai", "Maharashtra"),
    "bombay": ("Mumbai", "Maharashtra"),
    "navi mumbai": ("Navi Mumbai", "Maharashtra"),
    "delhi": ("Delhi", "Delhi NCR"),
    "new delhi": ("New Delhi", "Delhi NCR"),
    "noida": ("Noida", "Uttar Pradesh"),
    "greater noida": ("Greater Noida", "Uttar Pradesh"),
    "gurugram": ("Gurugram", "Haryana"),
    "gurgaon": ("Gurugram", "Haryana"),
    "faridabad": ("Faridabad", "Haryana"),
    "ghaziabad": ("Ghaziabad", "Uttar Pradesh"),
    "ahmedabad": ("Ahmedabad", "Gujarat"),
    "gandhinagar": ("Gandhinagar", "Gujarat"),
    "vadodara": ("Vadodara", "Gujarat"),
    "surat": ("Surat", "Gujarat"),
    "kolkata": ("Kolkata", "West Bengal"),
    "calcutta": ("Kolkata", "West Bengal"),
    "indore": ("Indore", "Madhya Pradesh"),
    "bhopal": ("Bhopal", "Madhya Pradesh"),
    "jaipur": ("Jaipur", "Rajasthan"),
    "chandigarh": ("Chandigarh", "Chandigarh"),
    "mohali": ("Mohali", "Punjab"),
    "bhubaneswar": ("Bhubaneswar", "Odisha"),
    "lucknow": ("Lucknow", "Uttar Pradesh"),
    "kanpur": ("Kanpur", "Uttar Pradesh"),
    "nagpur": ("Nagpur", "Maharashtra"),
    "nashik": ("Nashik", "Maharashtra"),
    "patna": ("Patna", "Bihar"),
    "guwahati": ("Guwahati", "Assam"),
}

CITY_SYNONYMS: Dict[str, list[str]] = {
    "bengaluru": ["bengaluru", "bangalore", "blr"],
    "bangalore": ["bengaluru", "bangalore", "blr"],
    "chennai": ["chennai", "madras", "maa"],
    "madras": ["chennai", "madras", "maa"],
    "coimbatore": ["coimbatore", "cbe", "kovai"],
    "hyderabad": ["hyderabad", "secunderabad", "hyd"],
    "secunderabad": ["hyderabad", "secunderabad", "hyd"],
    "cuddalore": ["cuddalore"],
    "puducherry": ["puducherry", "pondicherry", "pondy"],
    "pondicherry": ["puducherry", "pondicherry", "pondy"],
    "kochi": ["kochi", "cochin", "cok"],
    "cochin": ["kochi", "cochin", "cok"],
    "mysuru": ["mysuru", "mysore"],
    "mysore": ["mysuru", "mysore"],
    "thiruvananthapuram": ["thiruvananthapuram", "trivandrum"],
    "trivandrum": ["thiruvananthapuram", "trivandrum"],
    "madurai": ["madurai"],
    "salem": ["salem"],
    "tiruchirappalli": ["tiruchirappalli", "trichy"],
    "trichy": ["tiruchirappalli", "trichy"],
    "mangaluru": ["mangaluru", "mangalore"],
    "mangalore": ["mangaluru", "mangalore"],
    "kozhikode": ["kozhikode", "calicut"],
    "calicut": ["kozhikode", "calicut"],
    "visakhapatnam": ["visakhapatnam", "vizag"],
    "vizag": ["visakhapatnam", "vizag"],
    "vijayawada": ["vijayawada"],
    "pune": ["pune", "pnq"],
    "mumbai": ["mumbai", "bombay", "navi mumbai", "bom"],
    "bombay": ["mumbai", "bombay", "navi mumbai", "bom"],
    "delhi": ["delhi", "new delhi", "noida", "greater noida", "gurugram", "gurgaon", "delhi ncr", "ncr", "faridabad", "ghaziabad"],
    "new delhi": ["delhi", "new delhi", "noida", "greater noida", "gurugram", "gurgaon", "delhi ncr", "ncr"],
    "noida": ["noida", "greater noida", "delhi", "delhi ncr"],
    "gurugram": ["gurugram", "gurgaon", "delhi", "delhi ncr"],
    "gurgaon": ["gurugram", "gurgaon", "delhi", "delhi ncr"],
    "kolkata": ["kolkata", "calcutta"],
    "calcutta": ["kolkata", "calcutta"],
    "ahmedabad": ["ahmedabad", "gandhinagar"],
    "chandigarh": ["chandigarh", "mohali"],
    "remote": ["remote", "worldwide", "anywhere", "all locations", "global", "work from home"],
}


def get_city_synonyms(city_query: str) -> list[str]:
    """Returns all recognized search synonyms for a city or location query."""
    if not city_query:
        return []
    clean = city_query.strip().lower()
    if clean in CITY_SYNONYMS:
        return CITY_SYNONYMS[clean]
    for canon, aliases in CITY_SYNONYMS.items():
        if clean in aliases:
            return aliases
    return [clean]


RESTRICTED_OVERSEAS_REGIONS = (
    "united states only", "usa only", "us only", "canada only", "uk only", "united kingdom only",
    "europe only", "emea only", "north america only", "latin america only", "latam only",
    "australia only", "japan only", "singapore only", "germany only"
)

OVERSEAS_COUNTRIES = (
    "united states", "usa", "canada", "united kingdom", "uk", "germany", "france",
    "spain", "portugal", "italy", "netherlands", "ireland", "poland", "sweden",
    "australia", "japan", "singapore", "new zealand", "brazil", "greece", "switzerland",
    "austria", "belgium", "denmark", "norway", "finland", "mexico", "israel", "philippines",
    "vietnam", "argentina", "chile", "colombia", "latam", "apac", "emea", "europe",
    "asia-pacific", "taiwan", "south korea", "korea", "indonesia", "malaysia", "thailand",
    "uae", "dubai", "south africa", "egypt", "turkey", "czech republic", "hungary", "romania", "bulgaria"
)

US_STATE_CODES = (
    "ca", "ny", "tx", "fl", "il", "pa", "oh", "ga", "nc", "mi", "nj", "va", "wa",
    "az", "ma", "tn", "in", "mo", "md", "wi", "co", "mn", "sc", "al", "la", "ky",
    "or", "ok", "ct", "ut", "ia", "nv", "ar", "ms", "ks", "nm", "ne", "id", "wv",
    "hi", "nh", "me", "ri", "mt", "de", "sd", "nd", "ak", "dc", "vt", "wy"
)


def classify_geographic_priority(
    location: str,
    work_arrangement: str = "",
    description: str = ""
) -> Dict[str, Any]:
    """Analyzes job location, work arrangement, and description to determine:
    1. geographic_priority (1, 2, or 3)
    2. geographic_tier_label
    3. location_eligibility_status
    4. city, state, country
    5. remote_eligibility
    6. geo_score (0.0 to 10.0)
    7. geo_notes
    """
    loc_clean = (location or "").strip()
    loc_lower = loc_clean.lower()
    arr_lower = (work_arrangement or "").strip().lower()
    desc_lower = (description or "").lower()
    full_text = f"{loc_lower} {arr_lower} {desc_lower}"

    is_remote = "remote" in arr_lower or "remote" in loc_lower or "work from home" in full_text
    is_hybrid = "hybrid" in arr_lower or "hybrid" in loc_lower

    # 1. Check for explicit overseas restriction
    if any(r in loc_lower for r in RESTRICTED_OVERSEAS_REGIONS):
        return {
            "geographic_priority": 4,
            "geographic_tier_label": GEO_PRIORITY_LABELS[4],
            "location_eligibility_status": "RESTRICTED_NON_INDIA",
            "city": "International",
            "state": "Non-India",
            "country": "International",
            "remote_eligibility": "RESTRICTED_NON_INDIA",
            "geo_score": 0.0,
            "geo_notes": f"Explicitly restricted to overseas region: {loc_clean}",
            "is_disqualified": True,
            "disqualifier_reason": f"Location restricted outside India ({loc_clean})"
        }

    # 2. Check for explicit overseas country / US states in location without India mention
    has_us_state = any(re.search(r",\s*" + re.escape(code) + r"\b", loc_lower) for code in US_STATE_CODES)
    is_overseas_country = any(c in loc_lower for c in OVERSEAS_COUNTRIES) or has_us_state
    has_visa_or_relocation = any(
        kw in full_text for kw in (
            "visa sponsorship", "relocation provided", "relocation package",
            "visa support", "international applicants welcome"
        )
    )

    if is_overseas_country and "india" not in loc_lower:
        if has_visa_or_relocation:
            return {
                "geographic_priority": 4,
                "geographic_tier_label": GEO_PRIORITY_LABELS[4],
                "location_eligibility_status": "VERIFIED_INTERNATIONAL_ELIGIBLE",
                "city": loc_clean,
                "state": "International",
                "country": "Overseas",
                "remote_eligibility": "VISA_SPONSORED_OR_RELOCATION",
                "geo_score": 4.0,
                "geo_notes": f"International location with visa/relocation support: {loc_clean}",
                "is_disqualified": False,
                "disqualifier_reason": None
            }
        else:
            return {
                "geographic_priority": 4,
                "geographic_tier_label": GEO_PRIORITY_LABELS[4],
                "location_eligibility_status": "INELIGIBLE_OVERSEAS",
                "city": loc_clean,
                "state": "International",
                "country": "Overseas",
                "remote_eligibility": "RESTRICTED_NON_INDIA",
                "geo_score": 0.0,
                "geo_notes": f"Overseas location without confirmed India eligibility: {loc_clean}",
                "is_disqualified": True,
                "disqualifier_reason": f"Location restricted outside India ({loc_clean})"
            }

    # 3. Check for explicit South Indian Primary Cities (Priority 1)
    for token, (city_name, state_name) in P1_PRIMARY_CITIES.items():
        if re.search(r"\b" + re.escape(token) + r"\b", loc_lower):
            arrangement_type = "Remote" if is_remote else ("Hybrid" if is_hybrid else "On-site")
            return {
                "geographic_priority": 1,
                "geographic_tier_label": GEO_PRIORITY_LABELS[1],
                "location_eligibility_status": "VERIFIED_INDIA_ELIGIBLE",
                "city": city_name,
                "state": state_name,
                "country": "India",
                "remote_eligibility": "INDIA_PERMITTED" if is_remote else "NOT_REMOTE",
                "geo_score": 10.0,
                "geo_notes": f"Primary South Indian Tech Hub: {city_name}, {state_name} ({arrangement_type})",
                "is_disqualified": False,
                "disqualifier_reason": None
            }

    # 4. Check for other South Indian Cities (Priority 2 - Regional & Home Hubs)
    for token, (city_name, state_name) in P1_OTHER_SOUTH_CITIES.items():
        if re.search(r"\b" + re.escape(token) + r"\b", loc_lower):
            arrangement_type = "Remote" if is_remote else ("Hybrid" if is_hybrid else "On-site")
            score = 9.0 if token in ("cuddalore", "puducherry", "pondicherry") else 8.5
            return {
                "geographic_priority": 2,
                "geographic_tier_label": GEO_PRIORITY_LABELS[2],
                "location_eligibility_status": "VERIFIED_INDIA_ELIGIBLE",
                "city": city_name,
                "state": state_name,
                "country": "India",
                "remote_eligibility": "INDIA_PERMITTED" if is_remote else "NOT_REMOTE",
                "geo_score": score,
                "geo_notes": f"South Indian Location: {city_name}, {state_name} ({arrangement_type})",
                "is_disqualified": False,
                "disqualifier_reason": None
            }

    # 5. Check for Tamil Nadu / Karnataka / Telangana / Kerala / Andhra regional mention (Priority 2)
    if any(s in loc_lower for s in ("tamil nadu", "tamilnadu", "karnataka", "telangana", "kerala", "andhra pradesh")):
        return {
            "geographic_priority": 2,
            "geographic_tier_label": GEO_PRIORITY_LABELS[2],
            "location_eligibility_status": "VERIFIED_INDIA_ELIGIBLE",
            "city": "South India",
            "state": "South India",
            "country": "India",
            "remote_eligibility": "INDIA_PERMITTED" if is_remote else "NOT_REMOTE",
            "geo_score": 8.5,
            "geo_notes": f"South Indian State specified: {loc_clean}",
            "is_disqualified": False,
            "disqualifier_reason": None
        }

    # 6. Check for Other Indian Tech Hubs (Priority 3)
    for token, (city_name, state_name) in P2_INDIAN_CITIES.items():
        if re.search(r"\b" + re.escape(token) + r"\b", loc_lower):
            arrangement_type = "Remote" if is_remote else ("Hybrid" if is_hybrid else "On-site")
            return {
                "geographic_priority": 3,
                "geographic_tier_label": GEO_PRIORITY_LABELS[3],
                "location_eligibility_status": "VERIFIED_INDIA_ELIGIBLE",
                "city": city_name,
                "state": state_name,
                "country": "India",
                "remote_eligibility": "INDIA_PERMITTED" if is_remote else "NOT_REMOTE",
                "geo_score": 7.0,
                "geo_notes": f"Other Indian Tech Hub: {city_name}, {state_name} ({arrangement_type})",
                "is_disqualified": False,
                "disqualifier_reason": None
            }

    # 7. Generic India mention
    if "india" in loc_lower:
        arrangement_type = "Remote" if is_remote else ("Hybrid" if is_hybrid else "On-site")
        # If remote in India -> Priority 1
        if is_remote:
            return {
                "geographic_priority": 1,
                "geographic_tier_label": GEO_PRIORITY_LABELS[1],
                "location_eligibility_status": "VERIFIED_INDIA_ELIGIBLE",
                "city": "Remote",
                "state": "India",
                "country": "India",
                "remote_eligibility": "INDIA_PERMITTED",
                "geo_score": 10.0,
                "geo_notes": "India-wide Remote position",
                "is_disqualified": False,
                "disqualifier_reason": None
            }
        return {
            "geographic_priority": 3,
            "geographic_tier_label": GEO_PRIORITY_LABELS[3],
            "location_eligibility_status": "VERIFIED_INDIA_ELIGIBLE",
            "city": "India",
            "state": "India",
            "country": "India",
            "remote_eligibility": "NOT_REMOTE",
            "geo_score": 7.0,
            "geo_notes": f"India general location: {loc_clean} ({arrangement_type})",
            "is_disqualified": False,
            "disqualifier_reason": None
        }

    # 8. Check for Confirmed Worldwide / India Remote (in location or arrangement)
    has_explicit_worldwide_remote = (
        is_remote and any(
            marker in loc_lower for marker in (
                "worldwide", "anywhere", "global remote", "remote worldwide", "anywhere in india"
            )
        )
    )
    if has_explicit_worldwide_remote:
        return {
            "geographic_priority": 1,
            "geographic_tier_label": GEO_PRIORITY_LABELS[1],
            "location_eligibility_status": "VERIFIED_INDIA_ELIGIBLE",
            "city": "Remote",
            "state": "All India / Worldwide",
            "country": "India",
            "remote_eligibility": "INDIA_PERMITTED",
            "geo_score": 10.0,
            "geo_notes": "Confirmed India-eligible Remote position (Worldwide or explicit India)",
            "is_disqualified": False,
            "disqualifier_reason": None
        }

    # 9. Ambiguous Remote or Unknown location
    if is_remote or loc_lower in ("remote", "unknown", ""):
        return {
            "geographic_priority": 4,
            "geographic_tier_label": GEO_PRIORITY_LABELS[4],
            "location_eligibility_status": "LOCATION_ELIGIBILITY_UNCONFIRMED",
            "city": "Remote (Unconfirmed)",
            "state": "Unknown",
            "country": "Unknown",
            "remote_eligibility": "LOCATION_ELIGIBILITY_UNCONFIRMED",
            "geo_score": 0.0,
            "geo_notes": "Ambiguous remote location: geographic eligibility for India is unconfirmed",
            "is_disqualified": False,
            "disqualifier_reason": None
        }

    # 10. Fallback: Unknown location
    return {
        "geographic_priority": 4,
        "geographic_tier_label": GEO_PRIORITY_LABELS[4],
        "location_eligibility_status": "LOCATION_ELIGIBILITY_UNCONFIRMED",
        "city": loc_clean or "Unknown",
        "state": "Unknown",
        "country": "Unknown",
        "remote_eligibility": "LOCATION_ELIGIBILITY_UNCONFIRMED",
        "geo_score": 0.0,
        "geo_notes": f"Unrecognized location: {loc_clean}. Eligibility unconfirmed.",
        "is_disqualified": False,
        "disqualifier_reason": None
    }
