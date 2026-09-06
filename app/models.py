"""Data contracts and Pydantic models for the AI Product Description Generator.

Defines strict input and output schemas, ensuring LLM output validity,
type safety, and clear runtime boundaries.
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# Supported categories and tones as types
CategoryType = Literal["electronics", "apparel", "home_goods"]
ToneType = Literal["professional", "casual", "persuasive", "minimal", "luxury", "technical"]


class ProductInput(BaseModel):
    """Input contract for product information provided to the generator."""
    product_name: str = Field(..., description="Name or title of the product")
    category: CategoryType = Field(..., description="Product category for specialized prompt guidance")
    features: list[str] = Field(..., description="List of verified, factual statements about the product")
    target_audience: Optional[str] = Field(default=None, description="Intended customer profile or demographic")
    tone: ToneType = Field(default="professional", description="Brand voice / copy tone")
    seo_keywords: list[str] = Field(default_factory=list, description="Target search keywords to weave in naturally")
    additional_notes: Optional[str] = Field(default=None, description="Optional constraints or context")

    @field_validator("product_name")
    @classmethod
    def validate_product_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("product_name cannot be empty or whitespace only")
        return v

    @field_validator("features")
    @classmethod
    def validate_features(cls, v: list[str]) -> list[str]:
        cleaned = [item.strip() for item in v if item and item.strip()]
        if not cleaned:
            raise ValueError("features must contain at least one non-empty factual statement")
        return cleaned

    @field_validator("seo_keywords")
    @classmethod
    def clean_keywords(cls, v: list[str]) -> list[str]:
        return [k.strip() for k in v if k and k.strip()]


class SEOData(BaseModel):
    """SEO metadata generated for search engines."""
    meta_title: str = Field(..., description="SEO title tag (recommended 30-60 characters)")
    meta_description: str = Field(..., description="SEO meta description (recommended 120-160 characters)")
    keywords_used: list[str] = Field(default_factory=list, description="Keywords naturally integrated into the copy")


class ProductMeta(BaseModel):
    """Metadata regarding the product generation context."""
    category: str = Field(..., description="Applied product category")
    tone: str = Field(..., description="Applied tone of voice")


class ProductDescription(BaseModel):
    """The structured output schema expected from the LLM."""
    title: str = Field(..., description="Storefront-ready product title")
    short_description: str = Field(..., description="Punchy, benefit-focused summary (2-3 sentences)")
    long_description: str = Field(..., description="Comprehensive, multi-paragraph product description")
    bullet_points: list[str] = Field(..., description="Scannable, feature-to-benefit bullet points")
    seo: SEOData = Field(..., description="SEO meta title, description, and keyword usage")
    product: ProductMeta = Field(..., description="Category and tone metadata")


class ValidationResult(BaseModel):
    """Outcome of deterministic checks performed on LLM output."""
    valid: bool = Field(..., description="True if no hard validation errors occurred")
    errors: list[str] = Field(default_factory=list, description="Hard errors that fail validation")
    warnings: list[str] = Field(default_factory=list, description="Soft warnings that flag non-critical advice")
    keyword_coverage: dict[str, bool] = Field(
        default_factory=dict,
        description="Mapping of supplied keywords to whether they were found in the generated copy"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic counts (character lengths, bullet counts, coverage ratio)"
    )


class GenerationResult(BaseModel):
    """End-to-end result returned by the generator pipeline."""
    product: Optional[ProductDescription] = Field(default=None, description="Generated product copy if successful")
    validation: ValidationResult = Field(..., description="Validation report")
    retries: int = Field(default=0, description="Number of repair retries performed")
    latency_ms: float = Field(default=0.0, description="End-to-end generation latency in milliseconds")
    raw_response: Optional[str] = Field(default=None, description="Raw LLM response string before parsing")
    error_message: Optional[str] = Field(default=None, description="Error explanation if generation failed completely")
