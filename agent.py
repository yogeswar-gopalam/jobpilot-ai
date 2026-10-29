
"""JobPilot AI — safe, explainable job matching tools."""

import re
from typing import Any


def split_terms(value: Any) -> list[str]:
    """Convert comma/newline-separated profile fields into unique terms."""
    if not value:
        return []

    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[,\n;|]", str(value))

    result = []
    seen = set()

    for part in parts:
        term = str(part).strip().lower()
        if term and term not in seen:
            result.append(term)
            seen.add(term)

    return result


def match_job(job: dict, profile: dict) -> dict:
    """
    Calculate an explainable keyword match score.
    This is a heuristic, not a guarantee of job suitability.
    """
    skills = split_terms(profile.get("skills", ""))
    roles = split_terms(profile.get("roles", ""))

    title = str(job.get("title", ""))
    description = str(job.get("description", ""))
    company = str(job.get("company", ""))
    location = str(job.get("location", ""))

    searchable_text = f"{title} {description}".lower()

    matched_skills = [
        skill for skill in skills if skill in searchable_text
    ]
    missing_skills = [
        skill for skill in skills if skill not in searchable_text
    ]

    role_match = any(role in title.lower() for role in roles)

    if skills:
        skill_score = round(100 * len(matched_skills) / len(skills))
    else:
        skill_score = None

    # Keep the score explainable and avoid pretending it is an AI prediction.
    if skill_score is None:
        score = 100 if role_match else 0
    else:
        score = round(skill_score * 0.8 + (20 if role_match else 0))

    reasons = []
    if matched_skills:
        reasons.append("Matching skills: " + ", ".join(matched_skills))
    if role_match:
        reasons.append("The job title matches a target role.")
    if missing_skills:
        reasons.append("Skills not found in the listing: " + ", ".join(missing_skills))

    return {
        "job_id": str(job.get("id", "")),
        "title": title,
        "company": company,
        "location": location,
        "url": str(job.get("url", "")),
        "match_score": max(0, min(100, score)),
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "role_match": role_match,
        "reasons": reasons,
        "score_type": "keyword heuristic; not a hiring probability",
    }


def rank_jobs(jobs: list[dict], profile: dict) -> list[dict]:
    """Rank job listings using the explainable matching function."""
    ranked = [match_job(job, profile) for job in jobs]

    return sorted(
        ranked,
        key=lambda item: item["match_score"],
        reverse=True,
    )

import re


import re

def fresher_eligibility(job: dict) -> dict:
    title = str(job.get("title", ""))
    description = str(job.get("description", ""))
    text = f"{title} {description}".lower()

    senior_patterns = [
        r"\bsenior\b", r"\bsr\.?\b", r"\blead\b",
        r"\bprincipal\b", r"\bstaff\b", r"\bmanager\b",
        r"\bdirector\b", r"\barchitect\b"
    ]

    if any(re.search(pattern, title.lower()) for pattern in senior_patterns):
        return {
            "eligibility": "not_fresher_friendly",
            "experience_note": "Senior-level title"
        }

    explicit_fresher = [
        "fresh graduate", "recent graduate", "entry-level",
        "entry level", "new graduate", "no experience required",
        "0-1 year", "0–1 year", "0 to 1 year",
        "early career", "junior"
    ]

    if any(term in text for term in explicit_fresher):
        return {
            "eligibility": "likely_fresher_friendly",
            "experience_note": "Listing contains an entry-level signal; verify full requirements"
        }

    years = re.findall(r"\b(\d+)\+?\s+years?\s+(?:of\s+)?experience\b", text)
    if years and max(map(int, years)) > 1:
        return {
            "eligibility": "requires_review",
            "experience_note": "Listing mentions experience beyond one year"
        }

    return {
        "eligibility": "experience_not_verified",
        "experience_note": "No clear fresher eligibility found in available listing text"
    }

def rank_fresher_jobs(jobs: list[dict], profile: dict) -> list[dict]:
    """Rank jobs and attach transparent fresher eligibility signals."""
    fresher_jobs = [
        job for job in jobs
        if is_fresher_friendly(job)
    ]

    ranked = rank_jobs(fresher_jobs, profile)

    for result in ranked:
        original = next(
            (
                job for job in fresher_jobs
                if str(job.get("id", "")) == result["job_id"]
            ),
            {}
        )
        result.update(fresher_eligibility(original))

    return ranked

