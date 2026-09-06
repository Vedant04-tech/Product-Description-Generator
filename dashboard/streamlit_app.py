"""Streamlit Dashboard for the AI-Powered eCommerce Product Description Generator.

Presentation layer adhering strictly to 06_UI_SPEC.md:
- Input form with sample product loader
- 4 Output tabs: Generated Content, SEO, JSON, Validation
- Real-time character badges, validation pass/fail indicators, export options
- Delegates all business logic to app.generator and app.validator
"""

import json
import os
import sys
from pathlib import Path
import streamlit as st

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import config
from app.generator import ProductGenerator
from app.models import ProductInput
from integrations import to_shopify_payload, to_woocommerce_payload


st.set_page_config(
    page_title="AI Product Description Generator",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for modern, professional styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.8rem;
    }
    .badge-pass {
        background-color: #DCFCE7;
        color: #15803D;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-fail {
        background-color: #FEE2E2;
        color: #B91C1C;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-warn {
        background-color: #FEF3C7;
        color: #B45309;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .char-count {
        font-size: 0.85rem;
        color: #64748B;
        font-style: italic;
    }
    .copy-box {
        background-color: #F8FAFC;
        border-left: 4px solid #3B82F6;
        padding: 1rem 1.25rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


def load_sample_products() -> list[dict]:
    """Load benchmark samples from samples.json."""
    samples_path = config.data_dir / "samples.json"
    if samples_path.exists():
        try:
            with open(samples_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


# Sidebar for sample product loading and configuration inspection
with st.sidebar:
    st.header("⚡ Quick Controls")
    samples = load_sample_products()
    
    if samples:
        st.subheader("Load Preset Sample")
        sample_options = [
            f"[{s['category'].upper()}] {s['product_name']}" for s in samples
        ]
        selected_sample_idx = st.selectbox(
            "Select a benchmark product",
            range(len(sample_options)),
            format_func=lambda i: sample_options[i],
        )

        if st.button("Load Selected Sample into Form", use_container_width=True):
            chosen = samples[selected_sample_idx]
            st.session_state["p_name"] = chosen["product_name"]
            st.session_state["p_category"] = chosen["category"]
            st.session_state["p_features"] = "\n".join(chosen["features"])
            st.session_state["p_audience"] = chosen.get("target_audience", "")
            st.session_state["p_tone"] = chosen.get("tone", "professional")
            st.session_state["p_keywords"] = ", ".join(chosen.get("seo_keywords", []))
            st.session_state["p_notes"] = chosen.get("additional_notes", "")
            st.rerun()

    st.markdown("---")
    st.subheader("⚙️ System Status")
    provider_configured = config.is_api_configured()
    if provider_configured:
        st.success(f"Provider Active: **{config.llm_provider.upper()}**\nModel: `{config.groq_model}`")
    else:
        st.warning("⚠️ API Key not detected in `.env`. Please configure `GROQ_API_KEY`.")

    st.markdown("---")
    st.caption("AI-Powered eCommerce Product Description Generator v1.0")


# Header
st.markdown('<div class="main-header">AI-Powered eCommerce Product Description Generator</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Generate structured, SEO-aware storefront copy from verified product facts using category-aware prompting and deterministic validation.</div>',
    unsafe_allow_html=True,
)

# Input Section
col_left, col_right = st.columns([1, 1], gap="medium")

with col_left:
    st.subheader("📝 Product Input Specification")

    product_name = st.text_input(
        "Product Name *",
        value=st.session_state.get("p_name", "AuraFlow ANC Wireless Over-Ear Headphones"),
        key="input_product_name",
        help="Official storefront name or model designation",
    )

    cat_options = ["electronics", "apparel", "home_goods"]
    current_cat = st.session_state.get("p_category", "electronics")
    cat_idx = cat_options.index(current_cat) if current_cat in cat_options else 0
    category = st.selectbox(
        "Category *",
        cat_options,
        index=cat_idx,
        key="input_category",
        help="Specialized category instructions loaded from JSON prompts",
    )

    default_features = (
        "Hybrid Active Noise Cancellation with dual feedback microphones\n"
        "40mm custom bio-cellulose dynamic drivers\n"
        "Up to 45 hours battery life with ANC off, 35 hours with ANC on\n"
        "USB-C fast charging: 10 minutes gives 4 hours playback\n"
        "Bluetooth 5.3 with multipoint pairing for two devices simultaneously\n"
        "Foldable design with memory foam protein leather earcups"
    )
    features_raw = st.text_area(
        "Verified Product Features (one per line) *",
        value=st.session_state.get("p_features", default_features),
        height=160,
        key="input_features",
        help="Strict closed-world policy: Only provided facts will be used in copy.",
    )

    sub_col1, sub_col2 = st.columns(2)
    with sub_col1:
        tones = ["professional", "casual", "persuasive", "minimal", "luxury", "technical"]
        current_tone = st.session_state.get("p_tone", "professional")
        tone_idx = tones.index(current_tone) if current_tone in tones else 0
        tone = st.selectbox("Tone of Voice", tones, index=tone_idx, key="input_tone")

    with sub_col2:
        target_audience = st.text_input(
            "Target Audience",
            value=st.session_state.get("p_audience", "Commuters, remote professionals, and audio enthusiasts"),
            key="input_audience",
        )

    seo_keywords_raw = st.text_input(
        "Target SEO Keywords (comma-separated)",
        value=st.session_state.get("p_keywords", "wireless headphones, ANC headphones, bluetooth over-ear, long battery life"),
        key="input_keywords",
    )

    additional_notes = st.text_input(
        "Additional Notes",
        value=st.session_state.get("p_notes", "Emphasize daily commuting comfort and clear microphone clarity."),
        key="input_notes",
    )

    generate_btn = st.button("🚀 Generate Description", type="primary", use_container_width=True)

# Process Generation
if generate_btn:
    features_list = [f.strip() for f in features_raw.split("\n") if f.strip()]
    keywords_list = [k.strip() for k in seo_keywords_raw.split(",") if k.strip()]

    if not product_name.strip():
        st.error("Please enter a valid product name.")
    elif not features_list:
        st.error("Please provide at least one verified product feature.")
    else:
        try:
            input_contract = ProductInput(
                product_name=product_name,
                category=category,
                features=features_list,
                target_audience=target_audience.strip() or None,
                tone=tone,
                seo_keywords=keywords_list,
                additional_notes=additional_notes.strip() or None,
            )

            generator = ProductGenerator()
            with st.spinner("Generating copy & executing deterministic validation..."):
                gen_result = generator.generate(input_contract)

            st.session_state["gen_result"] = gen_result
            st.session_state["last_input"] = input_contract

        except Exception as e:
            st.error(f"Execution failed: {e}")

# Output Section
with col_right:
    st.subheader("📋 Output & Diagnostics")

    result = st.session_state.get("gen_result")
    last_input = st.session_state.get("last_input")

    if result is None:
        st.info("👋 Fill in product details and click **Generate Description** to preview structured copy, SEO tags, and validation metrics.")
    else:
        product = result.product
        val = result.validation

        # Metric summary banner
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            if val.valid:
                st.markdown('<span class="badge-pass">✓ VALIDATED</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-fail">✕ FAILED VALIDATION</span>', unsafe_allow_html=True)
        with m_col2:
            st.metric("Retries / Repairs", result.retries)
        with m_col3:
            st.metric("Latency", f"{result.latency_ms:.0f} ms")

        # 4 Required Tabs
        tab_content, tab_seo, tab_json, tab_validation = st.tabs([
            "📄 Generated Content",
            "🔍 SEO",
            "💻 JSON",
            "🛡️ Validation",
        ])

        with tab_content:
            if product:
                st.markdown(f"### {product.title}")
                st.markdown(f'<div class="copy-box">{product.short_description}</div>', unsafe_allow_html=True)

                st.markdown("#### Key Highlights")
                for bullet in product.bullet_points:
                    st.markdown(f"- {bullet}")

                st.markdown("#### Detailed Overview")
                st.markdown(product.long_description)
            else:
                st.error("No valid product content generated.")
                if result.error_message:
                    st.caption(result.error_message)

        with tab_seo:
            if product and product.seo:
                meta_t = product.seo.meta_title
                t_len = len(meta_t)
                meta_d = product.seo.meta_description
                d_len = len(meta_d)

                st.markdown("**Meta Title**")
                t_badge = "badge-pass" if (30 <= t_len <= 60) else "badge-fail"
                st.markdown(f"`{meta_t}`")
                st.markdown(f'<span class="{t_badge}">{t_len} characters (Target: 30-60)</span>', unsafe_allow_html=True)

                st.markdown("---")
                st.markdown("**Meta Description**")
                d_badge = "badge-pass" if (120 <= d_len <= 160) else "badge-fail"
                st.markdown(f"`{meta_d}`")
                st.markdown(f'<span class="{d_badge}">{d_len} characters (Target: 120-160)</span>', unsafe_allow_html=True)

                st.markdown("---")
                st.markdown("**Keywords Integration**")
                st.write(f"Keywords reported used: `{', '.join(product.seo.keywords_used) if product.seo.keywords_used else 'None'}`")

                if val.keyword_coverage:
                    st.markdown("**Keyword Presence Analysis:**")
                    cov_cols = st.columns(2)
                    for i, (kw, found) in enumerate(val.keyword_coverage.items()):
                        c = cov_cols[i % 2]
                        if found:
                            c.markdown(f"- ✅ **{kw}**: Present")
                        else:
                            c.markdown(f"- ⚠️ **{kw}**: Missing")

        with tab_json:
            if product:
                formatted_json = json.dumps(product.model_dump(), indent=2)
                st.code(formatted_json, language="json")
                st.download_button(
                    label="📥 Download JSON",
                    data=formatted_json,
                    file_name=f"{product_name.lower().replace(' ', '_')}_copy.json",
                    mime="application/json",
                    use_container_width=True,
                )
            elif result.raw_response:
                st.code(result.raw_response, language="text")

        with tab_validation:
            st.markdown(f"**Overall Status:** {'✅ Passed' if val.valid else '❌ Failed'}")
            st.write(f"- **Bullet Points Count:** {val.metadata.get('bullet_count', 0)} (Allowed: 3-6)")
            st.write(f"- **Meta Title Length:** {val.metadata.get('meta_title_len', 0)} chars (Allowed: 30-60)")
            st.write(f"- **Meta Description Length:** {val.metadata.get('meta_desc_len', 0)} chars (Allowed: 120-160)")
            st.write(f"- **Keyword Coverage:** {val.metadata.get('coverage_ratio', 0.0):.0%}")

            if val.errors:
                st.error("**Errors Detected:**")
                for err in val.errors:
                    st.write(f"- {err}")

            if val.warnings:
                st.warning("**Advisory Warnings:**")
                for warn in val.warnings:
                    st.write(f"- {warn}")

            if not val.errors and not val.warnings:
                st.success("All deterministic rules satisfied without errors or warnings.")

        # Platform Export Section
        if product:
            st.markdown("---")
            st.subheader("📦 Platform Exports")
            exp_col1, exp_col2 = st.columns(2)
            with exp_col1:
                shopify_data = to_shopify_payload(product, last_input)
                st.download_button(
                    "🛍️ Shopify Payload (JSON)",
                    data=json.dumps(shopify_data, indent=2),
                    file_name="shopify_product.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with exp_col2:
                woo_data = to_woocommerce_payload(product, last_input)
                st.download_button(
                    "🛒 WooCommerce Payload (JSON)",
                    data=json.dumps(woo_data, indent=2),
                    file_name="woocommerce_product.json",
                    mime="application/json",
                    use_container_width=True,
                )
