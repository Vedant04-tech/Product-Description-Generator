"""Command-line interface for the AI Product Description Generator.

Supports both direct argument generation and an interactive terminal prompt
with sample product pre-loading.
"""

import argparse
import json
import sys
from typing import Optional

from app.config import config
from app.generator import ProductGenerator
from app.models import ProductInput
from integrations import to_shopify_payload, to_woocommerce_payload


def print_banner():
    print("=" * 70)
    print("  AI-POWERED ECOMMERCE PRODUCT DESCRIPTION GENERATOR (CLI)")
    print("=" * 70)


def interactive_mode() -> ProductInput:
    """Run interactive terminal prompt to gather product inputs."""
    print_banner()
    print("Select input mode:")
    print("1. Load pre-defined sample product (Quick test)")
    print("2. Enter custom product details manually")
    choice = input("Enter choice (1 or 2, default 1): ").strip() or "1"

    if choice == "1":
        samples_path = config.data_dir / "samples.json"
        with open(samples_path, "r", encoding="utf-8") as f:
            samples = json.load(f)

        print("\nAvailable Samples:")
        for idx, s in enumerate(samples[:10], start=1):
            print(f"  {idx}. [{s['category'].upper()}] {s['product_name']}")

        sample_idx = input(f"\nSelect sample (1-{min(10, len(samples))}, default 1): ").strip() or "1"
        try:
            selected = samples[int(sample_idx) - 1]
            return ProductInput(
                product_name=selected["product_name"],
                category=selected["category"],
                features=selected["features"],
                target_audience=selected.get("target_audience"),
                tone=selected.get("tone", "professional"),
                seo_keywords=selected.get("seo_keywords", []),
                additional_notes=selected.get("additional_notes"),
            )
        except Exception:
            print("Invalid selection, falling back to first sample.")
            selected = samples[0]
            return ProductInput(
                product_name=selected["product_name"],
                category=selected["category"],
                features=selected["features"],
                target_audience=selected.get("target_audience"),
                tone=selected.get("tone", "professional"),
                seo_keywords=selected.get("seo_keywords", []),
            )

    # Custom input
    print("\nEnter Product Details:")
    name = input("Product Name: ").strip()
    while not name:
        name = input("Product Name (required): ").strip()

    print("\nCategory:")
    print("1. electronics\n2. apparel\n3. home_goods")
    cat_map = {"1": "electronics", "2": "apparel", "3": "home_goods"}
    cat_choice = input("Select Category (1-3, default 1): ").strip() or "1"
    category = cat_map.get(cat_choice, "electronics")

    print("\nEnter Features (one per line, enter blank line to finish):")
    features = []
    while True:
        feat = input(f"Feature {len(features) + 1}: ").strip()
        if not feat:
            if features:
                break
            print("Please provide at least one feature.")
            continue
        features.append(feat)

    audience = input("Target Audience (optional): ").strip() or None

    print("\nTone:")
    print("1. professional  2. casual  3. persuasive  4. minimal  5. luxury  6. technical")
    tone_map = {
        "1": "professional", "2": "casual", "3": "persuasive",
        "4": "minimal", "5": "luxury", "6": "technical"
    }
    tone_choice = input("Select Tone (1-6, default 1): ").strip() or "1"
    tone = tone_map.get(tone_choice, "professional")

    keywords_raw = input("SEO Keywords (comma-separated, optional): ").strip()
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()] if keywords_raw else []

    notes = input("Additional Notes (optional): ").strip() or None

    return ProductInput(
        product_name=name,
        category=category,
        features=features,
        target_audience=audience,
        tone=tone,
        seo_keywords=keywords,
        additional_notes=notes,
    )


def display_result(result):
    """Print beautifully formatted result to terminal."""
    print("\n" + "=" * 70)
    print("  GENERATION RESULTS")
    print("=" * 70)

    if result.product:
        p = result.product
        print(f"\n[STOREFRONT TITLE]\n{p.title}\n")
        print(f"[SHORT DESCRIPTION]\n{p.short_description}\n")

        print("[KEY FEATURES & BULLETS]")
        for b in p.bullet_points:
            print(f"  * {b}")

        print(f"\n[DETAILED DESCRIPTION]\n{p.long_description}\n")

        print("-" * 70)
        print("[SEO METADATA]")
        print(f"  Meta Title:       {p.seo.meta_title} ({len(p.seo.meta_title)} chars)")
        print(f"  Meta Description: {p.seo.meta_description} ({len(p.seo.meta_description)} chars)")
        print(f"  Keywords Used:    {', '.join(p.seo.keywords_used)}")
    else:
        print("\n[ERROR] Generation failed.")
        if result.error_message:
            print(f"Details: {result.error_message}")

    print("-" * 70)
    print("[VALIDATION REPORT]")
    status = "PASSED" if result.validation.valid else "FAILED"
    print(f"  Status:             {status}")
    print(f"  Retries / Repairs:  {result.retries}")
    print(f"  Latency:            {result.latency_ms:.1f} ms")

    if result.validation.errors:
        print("\n  Errors:")
        for err in result.validation.errors:
            print(f"    - {err}")

    if result.validation.warnings:
        print("\n  Warnings:")
        for warn in result.validation.warnings:
            print(f"    - {warn}")

    if result.validation.keyword_coverage:
        print("\n  Keyword Coverage:")
        for kw, found in result.validation.keyword_coverage.items():
            mark = "FOUND" if found else "MISSING"
            print(f"    - '{kw}': {mark}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="AI Product Description Generator CLI")
    parser.add_argument("--name", type=str, help="Product Name")
    parser.add_argument("--category", choices=["electronics", "apparel", "home_goods"], help="Category")
    parser.add_argument("--features", nargs="+", help="Factual features (space separated or quoted)")
    parser.add_argument("--tone", choices=["professional", "casual", "persuasive", "minimal", "luxury", "technical"], default="professional", help="Tone")
    parser.add_argument("--keywords", nargs="*", default=[], help="Target SEO keywords")
    parser.add_argument("--audience", type=str, default=None, help="Target audience")
    parser.add_argument("--max-retries", type=int, default=None, help="Maximum validation repair attempts (0-3)")
    parser.add_argument("--export-shopify", type=str, default=None, help="Export Shopify payload to JSON file")
    parser.add_argument("--export-woo", type=str, default=None, help="Export WooCommerce payload to JSON file")
    parser.add_argument("--mock", action="store_true", help="Run with mock LLM for offline demonstration")
    parser.add_argument("--interactive", action="store_true", help="Launch interactive prompt")
    args = parser.parse_args()

    if args.interactive or not (args.name and args.category and args.features):
        input_data = interactive_mode()
    else:
        input_data = ProductInput(
            product_name=args.name,
            category=args.category,
            features=args.features,
            target_audience=args.audience,
            tone=args.tone,
            seo_keywords=args.keywords,
        )

    print(f"\nGenerating description for '{input_data.product_name}'...")
    if args.mock:
        from evaluation import MockLLM
        generator = ProductGenerator(llm=MockLLM(mode="v3"))
    else:
        generator = ProductGenerator()
    result = generator.generate(input_data, max_retries=args.max_retries)

    display_result(result)

    if result.product:
        if args.export_shopify:
            shopify_payload = to_shopify_payload(result.product, input_data)
            with open(args.export_shopify, "w", encoding="utf-8") as f:
                json.dump(shopify_payload, f, indent=2)
            print(f"Shopify payload written to: {args.export_shopify}")

        if args.export_woo:
            woo_payload = to_woocommerce_payload(result.product, input_data)
            with open(args.export_woo, "w", encoding="utf-8") as f:
                json.dump(woo_payload, f, indent=2)
            print(f"WooCommerce payload written to: {args.export_woo}")


if __name__ == "__main__":
    main()
