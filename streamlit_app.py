# Matador: Streamlit App for Local Patron & Competitor Analysis
import streamlit as st
import requests
from openai import OpenAI
import json
from bs4 import BeautifulSoup

# ---------- CONFIG ----------
st.set_page_config(page_title="Matador: Local Audience Profiler", layout="wide")

# ---------- OPENAI CLIENT ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- APP HEADER ----------
st.title("💃🏻 Matador")
st.subheader("Command the Crowd.")
st.write("Enter up to 5 US ZIP codes to generate local audience personas and analyze competitive restaurant brands.")

# ---------- INPUT ----------
zip_codes_input = st.text_input("Enter up to 5 ZIP Codes, separated by commas")
user_notes = st.text_area("Add any known local insights, cultural notes, or behaviors (optional)")
mode = st.radio("Choose persona generation mode:", ["Cumulative (combined)", "Individual (per ZIP)"])

# Google-Aligned Service Styles
service_style_map = {
    "Full Service": ["restaurant", "casual_dining", "fine_dining"],
    "Fast Casual": ["restaurant", "meal_takeaway"],
    "Quick Serve (QSR)": ["fast_food", "meal_takeaway"],
    "Café / Coffee Shop": ["cafe", "coffee_shop"],
    "Bakery": ["bakery"],
    "Bar / Pub": ["bar", "pub"],
    "Buffet": ["buffet"],
    "Food Truck": ["food_truck"]
}

selected_service_styles = st.multiselect(
    "Select Service Style(s):",
    options=list(service_style_map.keys())
)

# Expanded Cuisine Types
cuisine_styles = st.multiselect(
    "Select Cuisine Type(s):",
    [
        "Mexican", "Chinese", "Japanese", "Italian", "Thai", "Vietnamese",
        "Indian", "American", "Korean", "Mediterranean", "Seafood",
        "Barbecue", "Vegan", "Vegetarian", "Burgers", "Pizza", "Coffee",
        "Bakery", "Sushi", "Middle Eastern", "Caribbean", "French", "Greek",
        "Soul Food", "Southern", "German", "Cuban", "Hawaiian", "Brazilian",
        "Spanish", "Turkish", "African", "Tapas", "Steakhouse", "Hot Pot"
    ]
)

competitor_mode = st.radio("Choose how to analyze competitors:", ["Auto via Google Places", "Manual Entry"])
manual_competitors = []

if competitor_mode == "Manual Entry":
    with st.expander("Add Manual Competitor Info"):
        for i in range(3):
            name = st.text_input(f"Competitor {i+1} Name", key=f"manual_name_{i}")
            website = st.text_input(f"Competitor {i+1} Website", key=f"manual_site_{i}")
            if name:
                manual_competitors.append({"name": name, "website": website})

# ---------- DATA FUNCTIONS ----------
def build_patron_prompt(zip_codes, user_notes, mode):
    return f"""
    You are an expert in psychographics, anthropology, and brand strategy.

    Based on the following data for a 10-mile radius around ZIP code(s): {', '.join(zip_codes)}
    - User Notes: {user_notes}

    Generate 3–5 audience personas with the following:
    1. Persona Name (must be a collective name like "Sun Chasers", not an individual name)
    2. Summary of their lifestyle and cultural tendencies
    3. Archetypal opportunity (what they're psychologically drawn to; choose 1 of the 12 Jungian archetypes but renamed as: Citizen, Sage, Rebel, Lover, Creator, Explorer, Innocent, Magician, Hero, Jester, Caregiver, Sovereign)
    4. Motivators (emotional + behavioral drivers)
    5. 2–3 influenced secondary groups
    6. 5 brands they love that reflect their values
    7. Estimated prevalence (% of total population they represent)
    """

# ---------- SEARCH TERM BUILD ----------
search_terms = []
for style in selected_service_styles:
    search_terms += service_style_map.get(style, [])
search_terms += cuisine_styles

# ---------- RUN BUTTON ----------
if st.button("Run Matador Analysis"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
    if not zip_codes:
        st.error("Please enter at least one ZIP code.")
    elif len(zip_codes) > 5:
        st.error("You can enter up to 5 ZIP codes only.")
    else:
        with st.spinner("Analyzing audience personas..."):
            prompt = build_patron_prompt(zip_codes, user_notes, mode)
            try:
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=2500
                )
                output = response.choices[0].message.content

                st.subheader("🎯 Patron Personas")
                personas = output.split("\n\n")
                for block in personas:
                    lines = block.strip().split("\n")
                    if not lines:
                        continue
                    header_line = lines[0]
                    name, prevalence = "Unknown", "?"
                    if " - " in header_line:
                        name, prevalence = header_line.split(" - ")
                    elif ":" in header_line:
                        name, prevalence = header_line.split(":")
                    name = name.strip()
                    prevalence = prevalence.strip().replace("Prevalence", "").replace("(", "").replace(")", "")

                    st.markdown(f"### {name} — {prevalence}")
                    st.markdown("\n".join([f"- {line.strip()}" for line in lines[1:] if line.strip()]))

            except Exception as e:
                st.error(f"Failed to generate personas: {e}")