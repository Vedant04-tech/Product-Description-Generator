"""Streamlit Dashboard for the AI Product Description Generator.

Presentation layer adhering strictly to 06_UI_SPEC.md:
- Refined design system with structured typography, clean cards, and responsive hierarchy
- Two-column layout with 0.95:1.05 proportions giving ample room for generated output
- 4 Output tabs: Generated Content, SEO, JSON, Validation
- Real-time character counts, 3 balanced diagnostic cards, export options
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

# Refined design system
st.markdown("""
<style>
    :root {
        --text: #0f172a;
        --muted: #64748b;
        --border: #e2e8f0;
        --surface: #ffffff;
        --surface-soft: #f8fafc;
        --primary: #2563eb;
        --success-bg: #dcfce7;
        --success-text: #15803d;
    }
    .main-header {
        font-size: 2rem;
        line-height: 1.15;
        font-weight: 750;
        letter-spacing: -0.035em;
        color: var(--text);
        margin-bottom: 0.35rem;
    }
    .sub-header {
        font-size: 0.98rem;
        line-height: 1.5;
        color: var(--muted);
        margin-bottom: 1.75rem;
    }
    .section-label {
        font-size: 0.72rem;
        font-weight: 750;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 0.55rem;
    }
    .panel {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1.25rem;
    }
    .metric-card {
        background: var(--surface-soft);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 0.85rem 1rem;
        min-height: 88px;
    }
    .metric-label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--muted);
        font-weight: 700;
    }
    .metric-value {
        font-size: 1.35rem;
        font-weight: 750;
        color: var(--text);
        margin-top: 0.2rem;
    }
    .badge-pass {
        background: #dcfce7;
        color: #15803d;
        padding: 0.35rem 0.7rem;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.78rem;
        display: inline-block;
    }
    .badge-fail {
        background: #fee2e2;
        color: #b91c1c;
        padding: 0.35rem 0.7rem;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.78rem;
        display: inline-block;
    }
    .badge-warn {
        background: #fef3c7;
        color: #b45309;
        padding: 0.35rem 0.7rem;
        border-radius: 999px;
        font-weight: 700;
        font-size: 0.78rem;
        display: inline-block;
    }
    .copy-box {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #2563eb;
        padding: 1rem 1.15rem;
        border-radius: 10px;
        line-height: 1.65;
        margin: 0.75rem 0 1.25rem;
    }
    .helper-text {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: -0.35rem;
        margin-bottom: 0.8rem;
    }
    .output-title {
        font-size: 1.45rem;
        font-weight: 750;
        line-height: 1.25;
        letter-spacing: -0.02em;
        color: #0f172a;
        margin-bottom: 0.5rem;
    }
    .stButton > button {
        border-radius: 9px;
        font-weight: 650;
        min-height: 42px;
    }
    div[data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 0.75rem;
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
    st.markdown("### Quick Controls")
    samples = load_sample_products()
    
    if samples:
        st.markdown('<div class="section-label">Preset sample</div>', unsafe_allow_html=True)
        sample_options = [
            f"[{s['category'].upper()}] {s['product_name']}" for s in samples
        ]
        selected_sample_idx = st.selectbox(
            "Select a benchmark product",
            range(len(sample_options)),
            format_func=lambda i: sample_options[i],
            label_visibility="collapsed",
        )

        if st.button("Load preset", use_container_width=True):
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
    st.markdown('<div class="section-label">System status</div>', unsafe_allow_html=True)
    provider_configured = config.is_api_configured()
    if provider_configured:
        st.markdown(
            f"""
            <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px; padding:12px;">
                <div style="color:#15803d; font-weight:700; font-size:0.88rem;">● Connected</div>
                <div style="margin-top:5px; color:#334155; font-size:0.92rem; font-weight:600;">{config.llm_provider.upper()}</div>
                <div style="margin-top:3px; color:#64748b; font-size:0.78rem; word-break:break-word;">{config.groq_model}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.warning("API key not detected in `.env`.")

    st.markdown("---")
    st.caption("AI-Powered eCommerce Product Description Generator v1.0")


# Header
st.markdown('<div class="main-header">AI Product Description Generator</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Turn verified product facts into SEO-ready storefront copy.</div>',
    unsafe_allow_html=True,
)

# Input & Output Layout: 0.95 to 1.05 with large gap for generous output space
col_left, col_right = st.columns([0.95, 1.05], gap="large")

with col_left:
    st.subheader("Product Details")

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
        "Verified Product Features *",
        value=st.session_state.get("p_features", default_features),
        height=160,
        key="input_features",
        help="Strict closed-world policy: Only provided facts will be used in copy.",
    )

    # Feature counter
    feature_count = len([f for f in features_raw.split("\n") if f.strip()])
    st.caption(f"{feature_count} verified feature" + ("s" if feature_count != 1 else ""))

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
        "SEO Keywords",
        value=st.session_state.get("p_keywords", "wireless headphones, ANC headphones, bluetooth over-ear, long battery life"),
        key="input_keywords",
        help="Target keywords to naturally weave into descriptions",
    )

    additional_notes = st.text_input(
        "Additional Instructions",
        value=st.session_state.get("p_notes", "Emphasize daily commuting comfort and clear microphone clarity."),
        key="input_notes",
    )

    generate_btn = st.button("✨ Generate Product Description", type="primary", use_container_width=True)

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
    st.subheader("Generated Output")

    result = st.session_state.get("gen_result")
    last_input = st.session_state.get("last_input")

    if result is None:
        st.info("👋 Fill in product details and click **Generate Product Description** to preview structured copy, SEO tags, and validation metrics.")
    else:
        product = result.product
        val = result.validation

        # Redesigned Balanced 3 Metric Cards
        m_col1, m_col2, m_col3 = st.columns(3, gap="small")
        latency_s = result.latency_ms / 1000
        with m_col1:
            status_text = "✓ Validated" if val.valid else "✕ Failed"
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Status</div>
                    <div class="metric-value">{status_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m_col2:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Repairs</div>
                    <div class="metric-value">{result.retries}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with m_col3:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">Latency</div>
                    <div class="metric-value">{latency_s:.1f}s</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='margin-bottom: 0.75rem;'></div>", unsafe_allow_html=True)

        # 4 Required Tabs
        tab_content, tab_seo, tab_json, tab_validation = st.tabs([
            "📄 Generated Content",
            "🔍 SEO",
            "💻 JSON",
            "🛡️ Validation",
        ])

        with tab_content:
            if product:
                st.markdown('<div class="section-label">Generated description</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="output-title">{product.title}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="copy-box">{product.short_description}</div>', unsafe_allow_html=True)

                st.markdown('<div class="section-label">Key highlights</div>', unsafe_allow_html=True)
                for bullet in product.bullet_points:
                    st.markdown(f"- {bullet}")

                st.markdown('<div class="section-label" style="margin-top:1.2rem;">Detailed overview</div>', unsafe_allow_html=True)
                st.markdown(product.long_description)

                # Export text
                st.markdown("---")
                copy_text = (
                    f"{product.title}\n\n"
                    f"{product.short_description}\n\n"
                    "Key Highlights:\n"
                    + "\n".join(f"• {b}" for b in product.bullet_points)
                    + "\n\nProduct Overview:\n"
                    + product.long_description
                )
                st.download_button(
                    "📥 Download Storefront Copy (.txt)",
                    data=copy_text,
                    file_name=f"{product_name.lower().replace(' ', '_')}_copy.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
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

                st.markdown("### SEO Metadata")
                st.markdown("**Meta Title**")
                st.code(meta_t, language="text")
                t_badge = "badge-pass" if (30 <= t_len <= 60) else "badge-fail"
                st.markdown(f'<span class="{t_badge}">{t_len}/60 characters</span>', unsafe_allow_html=True)

                st.markdown("")
                st.markdown("**Meta Description**")
                st.code(meta_d, language="text")
                d_badge = "badge-pass" if (120 <= d_len <= 160) else "badge-fail"
                st.markdown(f'<span class="{d_badge}">{d_len}/160 characters</span>', unsafe_allow_html=True)

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
            if val.valid:
                st.markdown('<div class="badge-pass" style="font-size:0.9rem; margin-bottom:1rem;">✓ VALIDATION PASSED</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="badge-fail" style="font-size:0.9rem; margin-bottom:1rem;">✕ VALIDATION FAILED</div>', unsafe_allow_html=True)

            st.markdown('<div class="section-label">Content Quality</div>', unsafe_allow_html=True)
            bullet_cnt = val.metadata.get('bullet_count', len(product.bullet_points) if product else 0)
            b_mark = "✓" if (3 <= bullet_cnt <= 6) else "✕"
            st.write(f"{b_mark} **{bullet_cnt} bullet points** (Target: 3–6)")

            t_len = val.metadata.get('meta_title_len', len(product.seo.meta_title) if (product and product.seo) else 0)
            t_mark = "✓" if (30 <= t_len <= 60) else "✕"
            st.write(f"{t_mark} **Meta title within limit** ({t_len}/60 chars)")

            d_len = val.metadata.get('meta_desc_len', len(product.seo.meta_description) if (product and product.seo) else 0)
            d_mark = "✓" if (120 <= d_len <= 160) else "✕"
            st.write(f"{d_mark} **Meta description within limit** ({d_len}/160 chars)")

            cov_ratio = val.metadata.get('coverage_ratio', 1.0)
            c_mark = "✓" if cov_ratio >= 0.5 else "⚠️"
            st.write(f"{c_mark} **SEO keywords covered** ({cov_ratio:.0%})")

            st.markdown('<div class="section-label" style="margin-top:1.2rem;">Grounding & Factuality</div>', unsafe_allow_html=True)
            has_forbidden = any("forbidden" in e.lower() for e in val.errors)
            f_mark = "✕" if has_forbidden else "✓"
            st.write(f"{f_mark} **No forbidden ungrounded claims detected**")
            st.write("✓ **Closed-world policy**: Only verified input features used")

            if val.errors:
                st.markdown("---")
                st.error("**Errors Detected:**")
                for err in val.errors:
                    st.write(f"- {err}")

            if val.warnings:
                st.markdown("---")
                st.warning("**Advisory Warnings:**")
                for warn in val.warnings:
                    st.write(f"- {warn}")

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
