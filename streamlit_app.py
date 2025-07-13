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

# ---------- SEARCH TERM BUILD ----------
search_terms = []
for style in selected_service_styles:
    search_terms += service_style_map.get(style, [])
search_terms += cuisine_styles

# ---------- PROMPT BUILD ----------
def build_patron_prompt(zip_codes, user_notes, mode):
    return f"""
    You are an expert in psychographics, anthropology, and brand strategy.

    Based on the following data for a 10-mile radius around ZIP code(s): {', '.join(zip_codes)}
    - User Notes: {user_notes}

    Generate 3–5 audience personas with the following:
    1. Persona Name (must be a collective name like \"Sun Chasers\", not an individual name)
    2. Summary of their lifestyle and cultural tendencies
    3. Archetypal opportunity (what they're psychologically drawn to; choose 1 of the 12 Jungian archetypes but renamed as: Citizen, Sage, Rebel, Lover, Creator, Explorer, Innocent, Magician, Hero, Jester, Caregiver, Sovereign)
    4. Motivators (emotional + behavioral drivers)
    5. 2–3 influenced secondary groups
    6. 5 brands they love that reflect their values
    7. Estimated prevalence (% of total population they represent)
    """
def get_lat_lon(zip_code):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={st.secrets['GOOGLE_API_KEY']}"
    response = requests.get(url)
    if response.status_code == 200:
        results = response.json().get("results")
        if results:
            location = results[0]["geometry"]["location"]
            return location["lat"], location["lng"]
    return None, None
# ---------- RESULT HANDLING ----------
if st.button("Generate Report"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
    if 1 <= len(zip_codes) <= 5:

        # --- Build search terms safely ---
        search_terms = []
        for s in selected_service_styles:
            search_terms += service_style_map.get(s, [])
        search_terms += cuisine_styles

        tabs = st.tabs(["Patrons", "Competition", "White Space"])

        with tabs[0]:
            with st.spinner("Generating audience personas..."):
                try:
                    prompt = build_patron_prompt(zip_codes, user_notes, mode)
                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.75,
                        max_tokens=1600
                    )
                    result = response.choices[0].message.content
                    personas = result.split("\n\n")
                    for p in personas:
                        st.markdown(p)
                except Exception as e:
                    st.error(f"Error generating personas: {e}")

        with tabs[1]:
            st.subheader("Top Competitor Analysis")
            all_competitors = []

            for zip_code in zip_codes:
                lat, lon = get_lat_lon(zip_code)
                if lat and lon and competitor_mode == "Auto via Google Places":
                    comps = get_places_data(lat, lon, search_terms)
                    all_competitors.extend(comps)

            all_competitors.extend(manual_competitors)

            # Deduplicate by name
            seen_names = set()
            unique_comps = []
            for comp in all_competitors:
                if comp["name"] not in seen_names:
                    unique_comps.append(comp)
                    seen_names.add(comp["name"])

            sorted_comps = sorted(
                unique_comps,
                key=lambda x: (x.get("rating", 0) or 0) * (x.get("review_count", 0) or 0),
                reverse=True
            )[:10]

            if sorted_comps:
                st.markdown(f"Found **{len(sorted_comps)}** unique competitors.")
                for comp in sorted_comps:
                    st.markdown(f"### {comp['name']}")
                    st.markdown(f"**Location:** {comp.get('vicinity', 'Manual Entry')}")
                    st.markdown(f"**Rating:** ⭐ {comp.get('rating', 'N/A')} ({comp.get('review_count', '0')} reviews)")
                    if comp.get("website"):
                        st.markdown(f"**Website:** [{comp['website']}]({comp['website']})")
                        website_text = get_website_text(comp['website'])
                        brand_analysis = analyze_brand_with_gpt(comp['name'], comp.get("vicinity", ""), website_text)
                        st.markdown(brand_analysis)

                        # Quick multi-unit detection
                        unit_check = "likely multi-unit" if "locations" in website_text.lower() or "find a" in website_text.lower() else "likely independent"
                        st.markdown(f"**Type:** {unit_check}")
                    else:
                        st.markdown("_No website available for this competitor._")
            else:
                st.warning("No competitors found based on your criteria.")

        with tabs[2]:
            st.subheader("White Space Opportunities")

            with st.spinner("Analyzing persona + competitor gaps..."):
                try:
                    # Combine persona and competitor traits for analysis
                    all_traits = []

                    # Pull traits from GPT-generated persona results
                    persona_text = result  # Reuse response from patron tab
                    all_traits.append("Patron Profiles:\n" + persona_text)

                    # Add up to 8 competitors’ summaries for token efficiency
                    for comp in sorted_comps[:8]:
                        if comp.get("website"):
                            text = get_website_text(comp['website'])
                            summary = analyze_brand_with_gpt(comp['name'], comp.get("vicinity", ""), text)
                            all_traits.append(f"Competitor: {comp['name']}\n{summary}")

                    joined_data = "\n\n".join(all_traits)

                    white_space_prompt = (
                        "You are a brand strategist tasked with finding white space opportunities in the local market.\n\n"
                        "Based on the following data, identify 3 potential brand personality trait combinations (3 traits each) that are:\n"
                        "- Underserved by existing competitors\n"
                        "- Aligned with audience needs and interests\n\n"
                        "For each combo:\n"
                        "1. List the 3 traits\n"
                        "2. Name the patron personas most likely to be attracted to that combo\n"
                        "3. Write a short description of what kind of brand could emerge from this\n\n"
                        f"Data to analyze:\n{joined_data}"
                    )

                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": white_space_prompt}],
                        temperature=0.7,
                        max_tokens=1000
                    )
                    st.markdown(response.choices[0].message.content)
                except Exception as e:
                    st.error(f"Error generating white space analysis: {e}")
    else:
        st.warning("Please enter between 1 and 5 ZIP codes.")
