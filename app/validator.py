"""Deterministic validation engine for product descriptions.

Treats LLM output as untrusted and verifies:
1. Field completeness and types.
2. Storefront and SEO character length constraints.
3. Bullet point count boundaries.
4. Keyword presence and coverage metrics.
5. Closed-world compliance and forbidden claim patterns.
"""

import json
import re
from pathlib import Path
from typing import Any, Optional

from app.config import config, ValidationThresholds
from app.models import ProductDescription, ProductInput, ValidationResult


def load_category_forbidden_claims(category: str, prompts_dir: Optional[Path] = None) -> list[str]:
    """Load the list of forbidden claims for a given category from its JSON config."""
    p_dir = prompts_dir or config.prompts_dir
    category_file = p_dir / f"{category}.json"
    if not category_file.exists():
        return []
    try:
        with open(category_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("forbidden_claims", [])
    except Exception:
        return []


def check_keyword_in_text(keyword: str, text: str) -> bool:
    """Case-insensitive check for keyword presence in text."""
    clean_kw = keyword.strip().lower()
    clean_text = text.lower()
    if not clean_kw:
        return False
    # Check substring or word boundary
    pattern = r"\b" + re.escape(clean_kw) + r"\b"
    return bool(re.search(pattern, clean_text) or clean_kw in clean_text)


def validate_product_description(
    description: ProductDescription,
    input_data: ProductInput,
    thresholds: Optional[ValidationThresholds] = None,
    prompts_dir: Optional[Path] = None,
) -> ValidationResult:
    """Perform deterministic validation on a generated ProductDescription against its input.

    Args:
        description: The structured ProductDescription returned by the LLM.
        input_data: The original verified ProductInput facts.
        thresholds: Configured validation limits (lengths, counts, ratios).
        prompts_dir: Path to directory containing category JSON prompts.

    Returns:
        ValidationResult with pass/fail status, errors, warnings, keyword coverage, and metadata.
    """
    t = thresholds or config.validation
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Completeness and Blank Fields (Hard Errors)
    if not description.title or not description.title.strip():
        errors.append("Product title is empty or whitespace.")
    if not description.short_description or not description.short_description.strip():
        errors.append("Short description is empty or whitespace.")
    if not description.long_description or not description.long_description.strip():
        errors.append("Long description is empty or whitespace.")
    if not description.bullet_points or not isinstance(description.bullet_points, list):
        errors.append("Bullet points must be a non-empty list.")

    # 2. Bullet count constraints (Hard Error if outside bounds)
    bullet_count = len(description.bullet_points) if description.bullet_points else 0
    if bullet_count < t.bullet_min_count or bullet_count > t.bullet_max_count:
        errors.append(
            f"Bullet points count ({bullet_count}) is outside allowed range "
            f"[{t.bullet_min_count}, {t.bullet_max_count}]."
        )
    for idx, bp in enumerate(description.bullet_points or []):
        if not bp or not bp.strip():
            errors.append(f"Bullet point #{idx + 1} is empty.")

    # 3. SEO Constraints
    meta_title = description.seo.meta_title.strip() if description.seo else ""
    meta_desc = description.seo.meta_description.strip() if description.seo else ""

    meta_title_len = len(meta_title)
    meta_desc_len = len(meta_desc)

    if not meta_title:
        errors.append("SEO meta_title is missing or empty.")
    elif meta_title_len < t.meta_title_min_len or meta_title_len > t.meta_title_max_len:
        errors.append(
            f"SEO meta_title length ({meta_title_len} chars) is outside required range "
            f"[{t.meta_title_min_len}, {t.meta_title_max_len}]."
        )

    if not meta_desc:
        errors.append("SEO meta_description is missing or empty.")
    elif meta_desc_len < t.meta_desc_min_len or meta_desc_len > t.meta_desc_max_len:
        errors.append(
            f"SEO meta_description length ({meta_desc_len} chars) is outside required range "
            f"[{t.meta_desc_min_len}, {t.meta_desc_max_len}]."
        )

    # 4. Keyword Coverage Analysis
    full_text = " ".join([
        description.title,
        description.short_description,
        description.long_description,
        " ".join(description.bullet_points or []),
        meta_title,
        meta_desc,
    ])

    keyword_coverage: dict[str, bool] = {}
    missing_keywords: list[str] = []

    for kw in input_data.seo_keywords:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        found = check_keyword_in_text(kw_clean, full_text)
        keyword_coverage[kw_clean] = found
        if not found:
            missing_keywords.append(kw_clean)

    total_kws = len(keyword_coverage)
    covered_kws = sum(1 for v in keyword_coverage.values() if v)
    coverage_ratio = (covered_kws / total_kws) if total_kws > 0 else 1.0

    if missing_keywords:
        warnings.append(
            f"SEO keywords not detected in generated copy: {', '.join(missing_keywords)}."
        )
    if total_kws > 0 and coverage_ratio < t.keyword_coverage_warning_ratio:
        warnings.append(
            f"SEO keyword coverage ({coverage_ratio:.0%}) is below recommended threshold "
            f"({t.keyword_coverage_warning_ratio:.0%})."
        )

    # 5. Closed-World & Forbidden Claims Checks
    forbidden_claims = load_category_forbidden_claims(input_data.category, prompts_dir)
    # Generic ungrounded superlatives that violate conservative commerce copy
    generic_forbidden = [
        "best on the market",
        "guaranteed to cure",
        "100% risk free",
        "unmatched superiority",
    ]
    all_forbidden = list(dict.fromkeys(forbidden_claims + generic_forbidden))

    full_text_lower = full_text.lower()
    for forbidden in all_forbidden:
        f_clean = forbidden.strip().lower()
        if f_clean and f_clean in full_text_lower:
            errors.append(
                f"Copy contains forbidden ungrounded claim: '{forbidden}'."
            )

    # 6. Metadata summary
    metadata: dict[str, Any] = {
        "meta_title_len": meta_title_len,
        "meta_desc_len": meta_desc_len,
        "bullet_count": bullet_count,
        "total_keywords": total_kws,
        "covered_keywords": covered_kws,
        "coverage_ratio": round(coverage_ratio, 2),
    }

    is_valid = len(errors) == 0

    return ValidationResult(
        valid=is_valid,
        errors=errors,
        warnings=warnings,
        keyword_coverage=keyword_coverage,
        metadata=metadata,
    )
