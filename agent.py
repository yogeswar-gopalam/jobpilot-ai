
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

def is_fresher_friendly(job: dict) -> bool:
    """Conservative title-based filter for entry-level opportunities."""
    title = str(job.get("title", "")).lower().strip()

    senior_patterns = [
        r"\bsenior\b",
        r"\bsr\.?\b",
        r"\blead\b",
        r"\bprincipal\b",
        r"\bstaff\b",
        r"\bmanager\b",
        r"\bdirector\b",
        r"\barchitect\b",
        r"\bhead of\b",
        r"\b[3-9]\+?\s*years?\b",
        r"\b1[0-9]\+?\s*years?\b",
    ]

    return not any(re.search(pattern, title) for pattern in senior_patterns)


def rank_fresher_jobs(jobs: list[dict], profile: dict) -> list[dict]:
    """Filter clearly senior job titles and rank remaining jobs."""
    fresher_jobs = [
        job for job in jobs
        if is_fresher_friendly(job)
    ]
    return rank_jobs(fresher_jobs, profile)
