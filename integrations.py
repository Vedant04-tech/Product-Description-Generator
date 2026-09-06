"""eCommerce Platform Adapters (Shopify & WooCommerce).

Transforms generated, validated ProductDescription models into ready-to-use API payloads
for major eCommerce storefront platforms without requiring live credentials.
"""

from typing import Any, Optional
from app.models import ProductDescription, ProductInput


def format_body_html(description: ProductDescription) -> str:
    """Render structured product copy into clean, semantic storefront HTML."""
    bullet_items = "\n".join(f"  <li>{bp}</li>" for bp in description.bullet_points)
    # Convert newlines in long description to paragraphs if needed
    paragraphs = [p.strip() for p in description.long_description.split("\n\n") if p.strip()]
    long_desc_html = "\n".join(f"<p>{p}</p>" for p in paragraphs) if paragraphs else f"<p>{description.long_description}</p>"

    return f"""<div class="product-description-container">
  <p class="product-short-summary"><strong>{description.short_description}</strong></p>
  <div class="product-features">
    <h4>Key Features & Highlights</h4>
    <ul>
{bullet_items}
    </ul>
  </div>
  <div class="product-details">
    <h4>Product Overview</h4>
    {long_desc_html}
  </div>
</div>"""


def to_shopify_payload(
    product: ProductDescription,
    input_data: Optional[ProductInput] = None,
    vendor: str = "Storefront",
) -> dict[str, Any]:
    """Convert generated product description into a Shopify REST / Admin API Product payload.

    Conforms to Shopify Product API resource structure:
    https://shopify.dev/docs/api/admin-rest/current/resources/product
    """
    category = input_data.category if input_data else product.product.category
    tags_list = list(product.seo.keywords_used)
    if input_data and input_data.seo_keywords:
        for kw in input_data.seo_keywords:
            if kw not in tags_list:
                tags_list.append(kw)

    body_html = format_body_html(product)

    return {
        "product": {
            "title": product.title,
            "body_html": body_html,
            "vendor": vendor,
            "product_type": category.replace("_", " ").title(),
            "status": "draft",
            "tags": ", ".join(tags_list),
            "metafields_global_title_tag": product.seo.meta_title,
            "metafields_global_description_tag": product.seo.meta_description,
            "metafields": [
                {
                    "namespace": "seo",
                    "key": "title",
                    "value": product.seo.meta_title,
                    "type": "single_line_text_field",
                },
                {
                    "namespace": "seo",
                    "key": "description",
                    "value": product.seo.meta_description,
                    "type": "multi_line_text_field",
                },
                {
                    "namespace": "ai_generator",
                    "key": "tone",
                    "value": product.product.tone,
                    "type": "single_line_text_field",
                },
            ],
        }
    }


def to_woocommerce_payload(
    product: ProductDescription,
    input_data: Optional[ProductInput] = None,
) -> dict[str, Any]:
    """Convert generated product description into a WooCommerce REST API Product payload.

    Conforms to WooCommerce v3 Product API resource structure:
    https://woocommerce.github.io/woocommerce-rest-api-docs/#product-properties
    """
    category = input_data.category if input_data else product.product.category
    bullet_items = "".join(f"<li>{bp}</li>" for bp in description_bullets(product))
    full_html = f"<ul>{bullet_items}</ul>\n<p>{product.long_description}</p>"

    tags = [{"name": kw} for kw in product.seo.keywords_used]

    return {
        "name": product.title,
        "type": "simple",
        "status": "draft",
        "short_description": f"<p>{product.short_description}</p>",
        "description": full_html,
        "categories": [
            {"name": category.replace("_", " ").title()}
        ],
        "tags": tags,
        "meta_data": [
            {
                "key": "_yoast_wpseo_title",
                "value": product.seo.meta_title,
            },
            {
                "key": "_yoast_wpseo_metadesc",
                "value": product.seo.meta_description,
            },
            {
                "key": "_ai_generated_tone",
                "value": product.product.tone,
            },
        ],
    }


def description_bullets(product: ProductDescription) -> list[str]:
    """Extract bullet points safely."""
    return product.bullet_points or []
