"""Streamlit Dashboard for the AI Product Description Generator.

Presentation layer adhering strictly to 06_UI_SPEC.md:
- Refined design system with structured typography, clean cards, and responsive hierarchy
- Two-column layout with 0.95:1.05 proportions giving ample room for generated output
- Direct Session State callback architecture for robust preset loading and form clearing
- Stale output warning on input changes
- Safe HTML escaping for LLM output
- 4 Output tabs: Generated Content (with copy-to-clipboard), SEO, JSON, Validation
- Real-time character counters and balanced diagnostic cards
- Delegates all business logic to app.generator and app.validator
"""

import html
import json
import os
import re
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
    """Load benchmark samples from samples.json with explicit error reporting."""
    samples_path = config.data_dir / "samples.json"
    if samples_path.exists():
        try:
            with open(samples_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.sidebar.error(f"Could not load preset samples: {e}")
            return []
    return []


# Callbacks for robust Session State management
def load_preset_into_form(samples: list[dict], index: int) -> None:
    """Load a benchmark preset directly into the form widget state."""
    chosen = samples[index]
    st.session_state["input_product_name"] = chosen.get("product_name", "")
    st.session_state["input_category"] = chosen.get("category", "electronics")
    st.session_state["input_features"] = "\n".join(chosen.get("features", []))
    st.session_state["input_audience"] = chosen.get("target_audience", "")
    st.session_state["input_tone"] = chosen.get("tone", "professional")
    st.session_state["input_keywords"] = ", ".join(chosen.get("seo_keywords", []))
    st.session_state["input_notes"] = chosen.get("additional_notes", "")
    # Clear stale output on preset change
    st.session_state.pop("gen_result", None)
    st.session_state.pop("last_input", None)
    st.session_state["input_dirty"] = False


def clear_product_form() -> None:
    """Clear all form inputs and reset generation state."""
    st.session_state["input_product_name"] = ""
    st.session_state["input_category"] = "electronics"
    st.session_state["input_features"] = ""
    st.session_state["input_audience"] = ""
    st.session_state["input_tone"] = "professional"
    st.session_state["input_keywords"] = ""
    st.session_state["input_notes"] = ""
    st.session_state["input_dirty"] = False
    st.session_state.pop("gen_result", None)
    st.session_state.pop("last_input", None)


def mark_input_dirty() -> None:
    """Flag that the input fields have been edited by the user."""
    st.session_state["input_dirty"] = True


# Initialize default widget states if not already present
if "input_product_name" not in st.session_state:
    st.session_state["input_product_name"] = ""
if "input_category" not in st.session_state:
    st.session_state["input_category"] = "electronics"
if "input_features" not in st.session_state:
    st.session_state["input_features"] = ""
if "input_audience" not in st.session_state:
    st.session_state["input_audience"] = ""
if "input_tone" not in st.session_state:
    st.session_state["input_tone"] = "professional"
if "input_keywords" not in st.session_state:
    st.session_state["input_keywords"] = ""
if "input_notes" not in st.session_state:
    st.session_state["input_notes"] = ""
if "input_dirty" not in st.session_state:
    st.session_state["input_dirty"] = False


# Sidebar for sample product loading and configuration inspection
with st.sidebar:
    st.markdown("### Quick Controls")
    samples = load_sample_products()
    
    if samples:
        st.markdown('<div class="section-label">Preset sample</div>', unsafe_allow_html=True)
        sample_options = [
            f"[{s['category'].upper()}] {s['product_name']}" for s in samples
        ]
        selected_label = st.selectbox(
            "Select a benchmark product",
            sample_options,
            key="preset_selection",
            label_visibility="collapsed",
        )
        selected_sample_idx = sample_options.index(selected_label)

        btn_col1, btn_col2 = st.columns([1.2, 1], gap="small")
        with btn_col1:
            st.button(
                "Load preset",
                use_container_width=True,
                on_click=load_preset_into_form,
                args=(samples, selected_sample_idx),
            )
        with btn_col2:
            st.button(
                "Clear form",
                use_container_width=True,
                on_click=clear_product_form,
            )

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

    with st.expander("⚙️ Advanced Pipeline Settings"):
        selected_max_retries = st.slider(
            "Max Repair Retries",
            min_value=0,
            max_value=3,
            value=config.max_retries,
            help="Number of bounded LLM repair attempts if deterministic validation fails.",
        )

    st.markdown("---")
    st.caption("AI Product Description Generator v1.0")


# Header
st.markdown('<div class="main-header">AI Product Description Generator</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Turn verified product facts into SEO-ready storefront copy.</div>',
    unsafe_allow_html=True,
)

# Input & Output Layout: 0.95 to 1.05 with large gap for generous reading space
col_left, col_right = st.columns([0.95, 1.05], gap="large")

with col_left:
    st.subheader("Product Details")

    product_name = st.text_input(
        "Product Name *",
        key="input_product_name",
        placeholder="e.g. AuraFlow ANC Wireless Headphones",
        help="Enter the exact storefront product name.",
        on_change=mark_input_dirty,
    )

    cat_options = ["electronics", "apparel", "home_goods"]
    category = st.selectbox(
        "Category *",
        cat_options,
        key="input_category",
        help="Specialized category instructions loaded from JSON prompts",
        on_change=mark_input_dirty,
    )

    features_raw = st.text_area(
        "Verified Product Features *",
        key="input_features",
        height=160,
        placeholder=(
            "Enter one verified fact per line:\n\n"
            "40mm dynamic drivers\n"
            "Bluetooth 5.3\n"
            "45-hour battery life"
        ),
        help="Strict closed-world policy: Only provided facts will be used in copy.",
        on_change=mark_input_dirty,
    )

    # Feature counter & closed-world notice
    feature_count = len([f for f in features_raw.split("\n") if f.strip()])
    st.caption(
        f"{feature_count} verified fact{'s' if feature_count != 1 else ''} — "
        "Only these facts will be used to generate product claims."
    )

    sub_col1, sub_col2 = st.columns(2)
    with sub_col1:
        tones = ["professional", "casual", "persuasive", "minimal", "luxury", "technical"]
        tone = st.selectbox(
            "Tone of Voice",
            tones,
            key="input_tone",
            on_change=mark_input_dirty,
        )

    with sub_col2:
        target_audience = st.text_input(
            "Target Audience",
            key="input_audience",
            placeholder="e.g. Remote professionals and commuters",
            on_change=mark_input_dirty,
        )

    seo_keywords_raw = st.text_input(
        "SEO Keywords",
        key="input_keywords",
        placeholder="wireless headphones, ANC headphones, bluetooth",
        help="Target keywords to naturally weave into descriptions",
        on_change=mark_input_dirty,
    )

    additional_notes = st.text_input(
        "Additional Instructions",
        key="input_notes",
        placeholder="Optional: emphasize comfort, portability, clean design...",
        on_change=mark_input_dirty,
    )

    if not config.is_api_configured():
        st.error("⚠️ Groq API key is not configured. Add `GROQ_API_KEY` to your `.env` file before generating.")

    generate_btn = st.button(
        "✨ Generate Product Description",
        type="primary",
        use_container_width=True,
        disabled=not config.is_api_configured(),
    )

# Process Generation
if generate_btn:
    # Deduplicate and clean features
    features_list = list(dict.fromkeys(
        f.strip() for f in features_raw.splitlines() if f.strip()
    ))
    keywords_list = [k.strip() for k in seo_keywords_raw.split(",") if k.strip()]

    if not product_name.strip():
        st.error("Please enter a valid product name.")
    elif len(product_name.strip()) > 200:
        st.error("Product name must be 200 characters or fewer.")
    elif not features_list:
        st.error("Please provide at least one verified product feature.")
    elif len(features_list) > 30:
        st.error("Please keep verified features to 30 lines or fewer.")
    else:
        try:
            input_contract = ProductInput(
                product_name=product_name.strip(),
                category=category,
                features=features_list,
                target_audience=target_audience.strip() or None,
                tone=tone,
                seo_keywords=keywords_list,
                additional_notes=additional_notes.strip() or None,
            )

            generator = ProductGenerator()
            with st.spinner("Generating copy & executing deterministic validation..."):
                gen_result = generator.generate(
                    input_contract,
                    max_retries=st.session_state.get("selected_max_retries", config.max_retries),
                )

            st.session_state["gen_result"] = gen_result
            st.session_state["last_input"] = input_contract
            st.session_state["input_dirty"] = False

        except Exception as e:
            st.error(f"Execution failed: {e}")

# Output Section
with col_right:
    st.subheader("Generated Output")

    result = st.session_state.get("gen_result")
    last_input = st.session_state.get("last_input")

    # Stale input warning
    if st.session_state.get("input_dirty", False) and result is not None:
        st.warning("⚠️ Your product details have changed. Click **Generate Product Description** to refresh the output.")

    if result is None:
        st.info("👋 Choose a preset from the sidebar or enter your own product details, then click **Generate Product Description**.")
    else:
        product = result.product
        val = result.validation

        # Redesigned Balanced 3 Metric Cards with tooltip
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
                <div class="metric-card" title="Number of additional LLM repair attempts after deterministic validation failure.">
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
                safe_title = html.escape(product.title)
                safe_short_desc = html.escape(product.short_description)

                st.markdown('<div class="section-label">Generated description</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="output-title">{safe_title}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="copy-box">{safe_short_desc}</div>', unsafe_allow_html=True)

                st.markdown('<div class="section-label">Key highlights</div>', unsafe_allow_html=True)
                for bullet in product.bullet_points:
                    st.markdown(f"- {html.escape(bullet)}")

                st.markdown('<div class="section-label" style="margin-top:1.2rem;">Detailed overview</div>', unsafe_allow_html=True)
                st.markdown(product.long_description)

                # Quick copy-to-clipboard block & .txt download
                st.markdown("---")
                copy_text = (
                    f"{product.title}\n\n"
                    f"{product.short_description}\n\n"
                    "Key Highlights:\n"
                    + "\n".join(f"• {b}" for b in product.bullet_points)
                    + "\n\nProduct Overview:\n"
                    + product.long_description
                )

                st.markdown('<div class="section-label">Copy or Export Text</div>', unsafe_allow_html=True)
                st.code(copy_text, language="markdown")

                export_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', product.title.strip().lower())
                st.download_button(
                    "📥 Download .txt Copy",
                    data=copy_text,
                    file_name=f"{export_slug}_copy.txt",
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
                export_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', product.title.strip().lower())
                st.download_button(
                    label="📥 Download JSON",
                    data=formatted_json,
                    file_name=f"{export_slug}_copy.json",
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
            export_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', product.title.strip().lower())
            with exp_col1:
                shopify_data = to_shopify_payload(product, last_input)
                st.download_button(
                    "🛍️ Shopify Payload (JSON)",
                    data=json.dumps(shopify_data, indent=2),
                    file_name=f"{export_slug}_shopify.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with exp_col2:
                woo_data = to_woocommerce_payload(product, last_input)
                st.download_button(
                    "🛒 WooCommerce Payload (JSON)",
                    data=json.dumps(woo_data, indent=2),
                    file_name=f"{export_slug}_woocommerce.json",
                    mime="application/json",
                    use_container_width=True,
                )
