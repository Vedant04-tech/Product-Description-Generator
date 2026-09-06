"""Comprehensive unit test suite for the AI Product Description Generator.

Runs 100% offline using mock LLMs. Tests:
- Pydantic model validation (input contracts, output contracts)
- Category prompt loading (electronics, apparel, home_goods)
- Prompt composition (tone, SEO, closed-world instructions)
- Deterministic validator (length checks, bullet limits, forbidden claims, keywords)
- Generator pipeline & bounded retry/repair
- Platform adapters (Shopify, WooCommerce)
"""

import json
from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError

from app.config import ValidationThresholds
from app.generator import (
    ProductGenerator,
    compose_repair_prompt,
    compose_system_prompt,
    compose_user_prompt,
    extract_json_from_text,
    load_category_config,
)
from app.models import (
    ProductDescription,
    ProductInput,
    ProductMeta,
    SEOData,
    ValidationResult,
)
from app.validator import validate_product_description
from integrations import to_shopify_payload, to_woocommerce_payload


# ============================================================================
# 1. Pydantic Model Tests
# ============================================================================

def test_product_input_valid():
    """Valid product input should instantiate successfully."""
    item = ProductInput(
        product_name="Pro Bass Earbuds",
        category="electronics",
        features=["Bluetooth 5.3", "30 hour battery"],
        target_audience="Gym enthusiasts",
        tone="casual",
        seo_keywords=["earbuds", "bass"],
    )
    assert item.product_name == "Pro Bass Earbuds"
    assert len(item.features) == 2
    assert item.tone == "casual"


def test_product_input_empty_name_fails():
    """Empty or whitespace-only product name must raise ValueError."""
    with pytest.raises(ValidationError):
        ProductInput(
            product_name="   ",
            category="electronics",
            features=["Feature 1"],
        )


def test_product_input_empty_features_fails():
    """Empty features list or list of blank strings must raise ValueError."""
    with pytest.raises(ValidationError):
        ProductInput(
            product_name="Test Product",
            category="electronics",
            features=[],
        )
    with pytest.raises(ValidationError):
        ProductInput(
            product_name="Test Product",
            category="electronics",
            features=["  ", ""],
        )


def test_product_input_invalid_category_fails():
    """Invalid category not in Literal must raise ValidationError."""
    with pytest.raises(ValidationError):
        ProductInput(
            product_name="Test Product",
            category="automotive",  # Unsupported
            features=["Feature 1"],
        )


def test_product_description_model():
    """Complete product description should validate cleanly."""
    desc = ProductDescription(
        title="Premium Wireless Headphones with ANC",
        short_description="Immerse yourself in crystal-clear audio with advanced noise cancellation.",
        long_description="These wireless headphones are designed for discerning listeners. Enjoy rich acoustics.",
        bullet_points=[
            "Active Noise Cancellation eliminates background distractions",
            "Long-lasting 30-hour battery life keeps music playing all day",
            "Memory foam cushions ensure cloud-like comfort"
        ],
        seo=SEOData(
            meta_title="Premium Wireless Headphones | ANC Audio",
            meta_description="Shop our premium wireless headphones with 30-hour battery and active noise cancellation. Free shipping.",
            keywords_used=["wireless headphones", "ANC audio"],
        ),
        product=ProductMeta(category="electronics", tone="professional"),
    )
    assert desc.title.startswith("Premium")
    assert len(desc.bullet_points) == 3
    assert desc.seo.meta_title == "Premium Wireless Headphones | ANC Audio"


# ============================================================================
# 2. Prompt Loading & Composition Tests
# ============================================================================

@pytest.mark.parametrize("category", ["electronics", "apparel", "home_goods"])
def test_load_category_config(category):
    """All 3 required categories must load successfully from JSON."""
    cfg = load_category_config(category)
    assert cfg["category"] == category
    assert "role" in cfg
    assert "category_instructions" in cfg
    assert "forbidden_claims" in cfg
    assert isinstance(cfg["forbidden_claims"], list)


def test_load_category_config_missing_fails():
    """Attempting to load a non-existent category must raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_category_config("non_existent_category")


def test_compose_system_prompt():
    """System prompt composition should inject category rules, tone, and forbidden claims."""
    cfg = load_category_config("electronics")
    prompt = compose_system_prompt(cfg, tone="luxury")

    assert "electronics" in prompt.lower()
    assert "LUXURY" in prompt
    assert "FORBIDDEN CLAIMS" in prompt
    assert "ZERO HALLUCINATION" in prompt
    assert "meta_title" in prompt


def test_compose_user_prompt():
    """User prompt must contain all verified features and keywords."""
    item = ProductInput(
        product_name="Eco Cotton T-Shirt",
        category="apparel",
        features=["100% organic cotton", "200 GSM weight"],
        seo_keywords=["organic cotton tee", "summer shirt"],
        tone="casual",
    )
    prompt = compose_user_prompt(item)
    assert "Eco Cotton T-Shirt" in prompt
    assert "100% organic cotton" in prompt
    assert "organic cotton tee" in prompt


def test_compose_repair_prompt():
    """Repair prompt must carry original facts and highlight validation failures."""
    item = ProductInput(
        product_name="Desk Lamp",
        category="home_goods",
        features=["Dimmable LED", "USB port"],
    )
    errors = ["SEO meta_title length (20 chars) is outside required range [30, 60]."]
    repair = compose_repair_prompt(item, "previous raw text", errors)

    assert "The previous response failed deterministic quality" in repair
    assert "SEO meta_title length (20 chars)" in repair
    assert "Dimmable LED" in repair
    assert "REPAIR INSTRUCTIONS" in repair


# ============================================================================
# 3. Deterministic Validator Tests
# ============================================================================

@pytest.fixture
def sample_valid_input():
    return ProductInput(
        product_name="Pro Bass Earbuds",
        category="electronics",
        features=["Bluetooth 5.3", "30 hour battery life", "IPX5 water resistant"],
        seo_keywords=["earbuds", "bluetooth"],
    )


@pytest.fixture
def sample_valid_description():
    return ProductDescription(
        title="Pro Bass Earbuds with Bluetooth 5.3",
        short_description="Experience exceptional sound and all-day endurance with Pro Bass Earbuds.",
        long_description="Engineered for athletes and commuters, Pro Bass Earbuds feature modern Bluetooth 5.3 connectivity. Enjoy 30 hours of playback with IPX5 water resistance.",
        bullet_points=[
            "Modern Bluetooth 5.3 provides dependable wireless pairing",
            "Up to 30 hours of total battery life on a single charge",
            "IPX5 water resistance protects against splashes and sweat",
            "Ergonomic fit designed for comfortable daily wear"
        ],
        seo=SEOData(
            meta_title="Pro Bass Earbuds | Wireless Bluetooth Audio",  # 45 chars (30-60)
            meta_description="Shop Pro Bass Earbuds featuring Bluetooth 5.3, 30 hours of battery life, and IPX5 water resistance for workouts and commute.",  # 125 chars (120-160)
            keywords_used=["earbuds", "bluetooth"],
        ),
        product=ProductMeta(category="electronics", tone="professional"),
    )


def test_validator_passes_valid_product(sample_valid_description, sample_valid_input):
    """A compliant product description must pass validation with 0 errors."""
    result = validate_product_description(sample_valid_description, sample_valid_input)
    assert result.valid is True
    assert len(result.errors) == 0
    assert result.metadata["bullet_count"] == 4
    assert result.metadata["coverage_ratio"] == 1.0


def test_validator_flags_short_meta_title(sample_valid_description, sample_valid_input):
    """Meta title under minimum length must fail validation."""
    sample_valid_description.seo.meta_title = "Too short"  # 9 chars < 30
    result = validate_product_description(sample_valid_description, sample_valid_input)
    assert result.valid is False
    assert any("meta_title length" in err for err in result.errors)


def test_validator_flags_invalid_bullet_count(sample_valid_description, sample_valid_input):
    """Bullet points fewer than 3 or greater than 6 must fail validation."""
    sample_valid_description.bullet_points = ["Single bullet"]
    result = validate_product_description(sample_valid_description, sample_valid_input)
    assert result.valid is False
    assert any("Bullet points count (1) is outside allowed range" in err for err in result.errors)


def test_validator_detects_forbidden_claims(sample_valid_description, sample_valid_input):
    """Detect forbidden ungrounded claims defined in category JSON."""
    # "best in class" is forbidden in electronics.json
    sample_valid_description.short_description = (
        "These are the best in class earbuds with top sound."
    )
    result = validate_product_description(sample_valid_description, sample_valid_input)
    assert result.valid is False
    assert any("forbidden ungrounded claim: 'best in class'" in err for err in result.errors)


def test_validator_missing_keywords_warning(sample_valid_description, sample_valid_input):
    """Missing supplied keywords should produce warnings, not fatal crashes."""
    sample_valid_input.seo_keywords = ["unheard_keyword_xyz", "bluetooth"]
    result = validate_product_description(sample_valid_description, sample_valid_input)
    assert result.keyword_coverage["unheard_keyword_xyz"] is False
    assert result.keyword_coverage["bluetooth"] is True
    assert any("SEO keywords not detected" in w for w in result.warnings)


# ============================================================================
# 4. Generator Pipeline with Mock LLM
# ============================================================================

def test_generator_successful_first_pass(sample_valid_input, sample_valid_description):
    """Generator should return successful result with 0 retries on clean output."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps(sample_valid_description.model_dump())
    mock_llm.invoke.return_value = mock_response

    generator = ProductGenerator(llm=mock_llm)
    result = generator.generate(sample_valid_input)

    assert result.product is not None
    assert result.validation.valid is True
    assert result.retries == 0
    assert result.latency_ms > 0


def test_generator_repair_loop_recovers(sample_valid_input, sample_valid_description):
    """Generator should trigger repair prompt when 1st attempt fails, and succeed on 2nd."""
    # Attempt 1: short meta_title (fails validation)
    bad_data = sample_valid_description.model_dump()
    bad_data["seo"]["meta_title"] = "Short Title"  # 11 chars
    resp1 = MagicMock(content=json.dumps(bad_data))

    # Attempt 2: valid meta_title
    good_data = sample_valid_description.model_dump()
    resp2 = MagicMock(content=json.dumps(good_data))

    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = [resp1, resp2]

    generator = ProductGenerator(llm=mock_llm)
    result = generator.generate(sample_valid_input)

    assert mock_llm.invoke.call_count == 2
    assert result.retries == 1
    assert result.validation.valid is True
    assert result.product.seo.meta_title == sample_valid_description.seo.meta_title


def test_generator_max_retries_exhaustion(sample_valid_input, sample_valid_description):
    """Generator must stop when max_retries is reached and return failure status."""
    bad_data = sample_valid_description.model_dump()
    bad_data["seo"]["meta_title"] = "Bad"
    resp = MagicMock(content=json.dumps(bad_data))

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = resp

    generator = ProductGenerator(llm=mock_llm)
    result = generator.generate(sample_valid_input)

    # 1 initial attempt + 2 retries = 3 calls
    assert mock_llm.invoke.call_count == 3
    assert result.retries == 2
    assert result.validation.valid is False


# ============================================================================
# 5. Integrations / Platform Adapters Tests
# ============================================================================

def test_to_shopify_payload(sample_valid_description, sample_valid_input):
    """Shopify payload must format HTML body, product type, and SEO metafields."""
    payload = to_shopify_payload(sample_valid_description, sample_valid_input)
    product = payload["product"]

    assert product["title"] == sample_valid_description.title
    assert "<div class=\"product-description-container\">" in product["body_html"]
    assert "<li>" in product["body_html"]
    assert product["product_type"] == "Electronics"
    assert product["metafields_global_title_tag"] == sample_valid_description.seo.meta_title
    assert len(product["metafields"]) == 3


def test_to_woocommerce_payload(sample_valid_description, sample_valid_input):
    """WooCommerce payload must format categories, tags, and Yoast meta keys."""
    payload = to_woocommerce_payload(sample_valid_description, sample_valid_input)

    assert payload["name"] == sample_valid_description.title
    assert payload["short_description"] == f"<p>{sample_valid_description.short_description}</p>"
    assert payload["categories"][0]["name"] == "Electronics"
    yoast_keys = [m["key"] for m in payload["meta_data"]]
    assert "_yoast_wpseo_title" in yoast_keys
    assert "_yoast_wpseo_metadesc" in yoast_keys
