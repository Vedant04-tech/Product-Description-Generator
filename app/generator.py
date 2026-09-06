"""LangChain-powered generation pipeline with dynamic prompt composition and bounded repair.

Orchestrates:
1. Category-specific JSON prompt loading.
2. Modular prompt assembly (Common + Category + Tone + SEO + Facts).
3. LLM invocation via LangChain (ChatGroq / ChatOpenAI).
4. Structured JSON extraction into Pydantic models.
5. Deterministic validation with bounded retry/repair on failure.
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.config import config, AppConfig
from app.models import (
    GenerationResult,
    ProductDescription,
    ProductInput,
    ValidationResult,
)
from app.validator import validate_product_description


TONE_INSTRUCTIONS = {
    "professional": (
        "Maintain an authoritative, polished, and confident voice. "
        "Use clear, industry-standard language suitable for discerning shoppers."
    ),
    "casual": (
        "Use a warm, friendly, conversational tone. "
        "Sound like an enthusiastic, knowledgeable peer recommending a favorite find."
    ),
    "persuasive": (
        "Focus on immediate value, utility, and conversion. "
        "Highlight practical problem-solving benefits with compelling action verbs."
    ),
    "minimal": (
        "Be crisp, concise, and direct. Avoid unnecessary fluff or adjective overload. "
        "Let the factual highlights speak for themselves."
    ),
    "luxury": (
        "Adopt an elevated, sophisticated, and elegant tone. "
        "Emphasize thoughtful design, refinement, and aesthetic appeal without inventing materials."
    ),
    "technical": (
        "Prioritize exact specifications, functionality, and performance attributes. "
        "Use precise technical terminology without embellishment or exaggeration."
    ),
}


def load_category_config(category: str, prompts_dir: Optional[Path] = None) -> dict[str, Any]:
    """Load category-specific instructions from the JSON prompt repository."""
    p_dir = prompts_dir or config.prompts_dir
    category_path = p_dir / f"{category}.json"
    if not category_path.exists():
        raise FileNotFoundError(f"Category prompt file not found at {category_path}")

    with open(category_path, "r", encoding="utf-8") as f:
        return json.load(f)


def compose_system_prompt(category_config: dict[str, Any], tone: str) -> str:
    """Compose system instructions combining common rules, category rules, and tone."""
    role = category_config.get(
        "role",
        "You are an expert eCommerce copywriter creating high-converting, factually grounded product descriptions."
    )
    objective = category_config.get(
        "objective",
        "Transform verified product facts into storefront-ready copy and SEO metadata."
    )
    category_instructions = "\n".join(
        f"- {inst}" for inst in category_config.get("category_instructions", [])
    )
    feature_rules = "\n".join(
        f"- {rule}" for rule in category_config.get("feature_to_benefit_rules", [])
    )
    forbidden_claims = ", ".join(
        f'"{fc}"' for fc in category_config.get("forbidden_claims", [])
    )
    tone_guidance = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["professional"])

    return f"""{role}

OBJECTIVE:
{objective}

STRICT CLOSED-WORLD FACTUALITY RULES (ZERO HALLUCINATION):
1. Use ONLY the facts explicitly provided in the product input.
2. NEVER invent specifications, compatibility, battery life, certifications, warranties, dimensions, or materials.
3. If an attribute or specification is not mentioned, omit it completely.
4. Convert factual features into practical benefits, but do NOT turn a feature into a guarantee.
5. FORBIDDEN CLAIMS (Do NOT use under any circumstances): {forbidden_claims}

CATEGORY-SPECIFIC INSTRUCTIONS:
{category_instructions}

FEATURE-TO-BENEFIT TRANSLATION RULES:
{feature_rules}

TONE & VOICE GUIDANCE:
Tone requested: {tone.upper()}
{tone_guidance}

SEO & FORMATTING RULES:
- Meta Title: strictly 30 to 60 characters in length.
- Meta Description: strictly 120 to 160 characters in length.
- Bullet Points: exactly 3 to 6 scannable, benefit-focused bullet items.
- SEO Keywords: weave the supplied target keywords naturally into the title, descriptions, or bullets without stuffing.

OUTPUT CONTRACT:
You MUST respond with a valid JSON object strictly conforming to the following JSON schema:
{{
  "title": "Storefront product title",
  "short_description": "Concise 2-3 sentence summary",
  "long_description": "Comprehensive, multi-paragraph product description",
  "bullet_points": ["Bullet 1", "Bullet 2", "Bullet 3"],
  "seo": {{
    "meta_title": "SEO title (30-60 chars)",
    "meta_description": "SEO description (120-160 chars)",
    "keywords_used": ["keyword1", "keyword2"]
  }},
  "product": {{
    "category": "{category_config.get('category', '')}",
    "tone": "{tone}"
  }}
}}
Return ONLY valid JSON. Do not include markdown code fences (```json), preamble, or commentary outside the JSON.
"""


def compose_user_prompt(input_data: ProductInput) -> str:
    """Compose the user prompt presenting the verified product facts."""
    features_formatted = "\n".join(f"- {f}" for f in input_data.features)
    keywords_formatted = ", ".join(input_data.seo_keywords) if input_data.seo_keywords else "None"
    audience = input_data.target_audience or "General eCommerce shoppers"
    notes = input_data.additional_notes or "None"

    return f"""GENERATE PRODUCT DESCRIPTION FOR:

Product Name: {input_data.product_name}
Category: {input_data.category}
Target Audience: {audience}
Requested Tone: {input_data.tone}
Target SEO Keywords: {keywords_formatted}
Additional Notes: {notes}

VERIFIED PRODUCT FACTS & FEATURES:
{features_formatted}

Please generate the complete, grounded product description JSON according to your system instructions.
"""


def compose_repair_prompt(
    input_data: ProductInput,
    previous_output: str,
    validation_errors: list[str],
) -> str:
    """Construct repair prompt containing original facts and specific validation failures."""
    features_formatted = "\n".join(f"- {f}" for f in input_data.features)
    errors_formatted = "\n".join(f"- {e}" for e in validation_errors)

    return f"""The previous response failed deterministic quality and schema validation with the following errors:
{errors_formatted}

PREVIOUS OUTPUT:
{previous_output}

REPAIR INSTRUCTIONS:
1. Correct the specific issues flagged above (e.g. adjust meta_title or meta_description character length, adjust bullet point count, or remove forbidden claims).
2. You MUST NOT invent new facts. Retain all original product facts strictly:
{features_formatted}
3. Maintain the requested category ({input_data.category}) and tone ({input_data.tone}).
4. Output ONLY the corrected, valid JSON object matching the required schema.
"""


def extract_json_from_text(text: str) -> dict[str, Any]:
    """Extract and parse JSON object from LLM response, stripping code blocks if present."""
    cleaned = text.strip()
    # Strip markdown code blocks
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback: search for first { and last }
        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise ValueError(f"Could not parse valid JSON from LLM response: {text[:200]}...")


class ProductGenerator:
    """Generates structured, validated eCommerce product descriptions."""

    def __init__(self, app_config: Optional[AppConfig] = None, llm: Optional[Any] = None):
        self.config = app_config or config
        self._llm = llm

    def get_llm(self) -> Any:
        """Initialize the LangChain chat model if not already set or injected."""
        if self._llm is not None:
            return self._llm

        if self.config.llm_provider == "groq" or (self.config.groq_api_key and not self.config.openai_api_key):
            from langchain_groq import ChatGroq
            return ChatGroq(
                api_key=self.config.groq_api_key,
                model_name=self.config.groq_model,
                temperature=self.config.groq_temperature,
                max_tokens=self.config.groq_max_tokens,
            )
        else:
            # OpenAI fallback if configured
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                api_key=self.config.openai_api_key,
                model_name=self.config.openai_model,
                temperature=self.config.openai_temperature,
            )

    def generate(self, input_data: ProductInput, max_retries: Optional[int] = None) -> GenerationResult:
        """Execute the full generation and validation pipeline with bounded repair."""
        start_time = time.perf_counter()
        retries = 0
        retries_limit = max_retries if max_retries is not None else self.config.max_retries

        # Load category config
        try:
            category_cfg = load_category_config(input_data.category, self.config.prompts_dir)
        except Exception as e:
            latency = (time.perf_counter() - start_time) * 1000
            val_res = ValidationResult(valid=False, errors=[f"Failed loading category config: {e}"])
            return GenerationResult(
                product=None,
                validation=val_res,
                retries=0,
                latency_ms=latency,
                error_message=str(e),
            )

        # Initial prompt composition
        system_content = compose_system_prompt(category_cfg, input_data.tone)
        user_content = compose_user_prompt(input_data)
        messages: list[BaseMessage] = [
            SystemMessage(content=system_content),
            HumanMessage(content=user_content),
        ]

        llm = self.get_llm()
        last_raw_response = ""
        current_description: Optional[ProductDescription] = None
        current_validation: Optional[ValidationResult] = None

        while retries <= retries_limit:
            try:
                response = llm.invoke(messages)
                raw_text = response.content if hasattr(response, "content") else str(response)
                last_raw_response = raw_text

                # Parse JSON into ProductDescription model
                parsed_json = extract_json_from_text(raw_text)
                current_description = ProductDescription(**parsed_json)

                # Deterministic validation
                current_validation = validate_product_description(
                    description=current_description,
                    input_data=input_data,
                    thresholds=self.config.validation,
                    prompts_dir=self.config.prompts_dir,
                )

                if current_validation.valid:
                    # Valid output on this attempt!
                    latency = (time.perf_counter() - start_time) * 1000
                    return GenerationResult(
                        product=current_description,
                        validation=current_validation,
                        retries=retries,
                        latency_ms=round(latency, 2),
                        raw_response=last_raw_response,
                    )

                # If invalid and we have retries remaining, prepare fresh repair prompt without context bloat
                if retries < retries_limit:
                    retries += 1
                    repair_text = compose_repair_prompt(
                        input_data=input_data,
                        previous_output=raw_text,
                        validation_errors=current_validation.errors,
                    )
                    messages = [
                        SystemMessage(content=system_content),
                        HumanMessage(content=repair_text),
                    ]
                else:
                    break

            except Exception as e:
                parse_err = f"Generation/Parsing error: {e}"
                if retries < retries_limit:
                    retries += 1
                    repair_text = compose_repair_prompt(
                        input_data=input_data,
                        previous_output=last_raw_response,
                        validation_errors=[parse_err],
                    )
                    messages = [
                        SystemMessage(content=system_content),
                        HumanMessage(content=repair_text),
                    ]
                else:
                    val_res = current_validation or ValidationResult(
                        valid=False,
                        errors=[parse_err],
                    )
                    latency = (time.perf_counter() - start_time) * 1000
                    return GenerationResult(
                        product=current_description,
                        validation=val_res,
                        retries=retries,
                        latency_ms=round(latency, 2),
                        raw_response=last_raw_response,
                        error_message=parse_err,
                    )

        # Reached after bounded retries without full validation pass
        latency = (time.perf_counter() - start_time) * 1000
        val_res = current_validation or ValidationResult(
            valid=False,
            errors=["Validation failed and max retries exhausted."],
        )
        return GenerationResult(
            product=current_description,
            validation=val_res,
            retries=retries,
            latency_ms=round(latency, 2),
            raw_response=last_raw_response,
        )
