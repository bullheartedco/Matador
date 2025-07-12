# Matador: Streamlit App for Local Patron & Competitor Analysis
import streamlit as st
import requests
from openai import OpenAI
import json
from bs4 import BeautifulSoup
import re

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

service_styles = st.multiselect(
    "Select Service Style(s):",
    ["Full Service", "Fast Casual", "Quick Service", "Café", "Bakery", "Bar", "Fine Dining"]
)

cuisine_styles = st.multiselect(
    "Select Cuisine Type(s):",
    [
        "Mexican", "Chinese", "Japanese", "Italian", "Thai", "Vietnamese",
        "Indian", "American", "Korean", "Mediterranean", "Seafood",
        "Barbecue", "Vegan", "Vegetarian", "Burgers", "Pizza", "Coffee", "Bakery"
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
def get_census_data(zip_code):
    url = "https://api.census.gov/data/2021/acs/acs5"
    params = {
        "get": "NAME,B01001_001E,B19013_001E,B02001_002E,B02001_003E,B02001_005E",
        "for": f"zip code tabulation area:{zip_code}",
        "key": st.secrets["CENSUS_API_KEY"]
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if len(data) > 1:
            labels = data[0]
            values = data[1]
            return dict(zip(labels, values))
    return None

def get_lat_lon(zip_code):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={st.secrets['GOOGLE_API_KEY']}"
    response = requests.get(url)
    if response.status_code == 200:
        results = response.json().get("results")
        if results:
            location = results[0]["geometry"]["location"]
            return location["lat"], location["lng"]
    return None, None

def classify_service_style(place):
    types = place.get("types", [])
    price = place.get("price_level", 2)
    rating = place.get("rating", 0)

    if "meal_takeaway" in types or "fast_food" in types or price <= 1:
        return "Quick Service"
    elif "restaurant" in types and price == 2 and rating >= 4.0:
        return "Fast Casual"
    elif "restaurant" in types and price >= 3:
        return "Full Service"
    elif "cafe" in types:
        return "Café"
    elif "bakery" in types:
        return "Bakery"
    elif "bar" in types:
        return "Bar"
    elif "restaurant" in types and price == 4 and rating >= 4.3:
        return "Fine Dining"
    else:
        return "Other"

def filter_competitors_by_service_style(competitors, selected_styles):
    return [c for c in competitors if c.get("service_classification") in selected_styles]

def build_patron_prompt(zip_codes, user_notes, mode):
    base = f"""
    You are a consumer behavior analyst helping a brand strategist understand the local market across these ZIP codes: {', '.join(zip_codes)}.

    Use the following insights and data from the U.S. Census and local observation notes:
    Notes: {user_notes}

    Output 5 persona profiles that are representative of the population across these ZIPs. For each include:
    - Persona Name (use descriptive names like "Sun Chasers")
    - Lifestyle Summary
    - Motivators (behavioral and emotional drivers)
    - Archetypal Opportunity (what they're psychologically drawn to)
    - 3 Personality Traits
    - Influenced Groups (2–3 audience types they influence)
    - 5 Brands They Love (based on personality + values)
    - Prevalence Score (estimate % in market)

    Then, provide whitespace analysis:
    - Suggest 3 different combinations of 3 unique personality traits that are not currently owned by local competitors
    - For each combo, list which Patron Personas would most likely be attracted to it
    - Include a short explanation for why this combo fills a whitespace gap in the market
    """
    return base

# ---------- RENDER PATRONS ----------
def render_persona_output(text):
    personas = re.split(r'\n(?=Persona Name\s*:\s*)', text.strip())
    for persona in personas:
        if not persona.strip():
            continue
        name_match = re.search(r'Persona Name\s*:\s*(.+)', persona)
        prevalence_match = re.search(r'Prevalence Score\s*:\s*(\d+%?)', persona)

        name = name_match.group(1).strip() if name_match else "Unnamed Persona"
        prevalence = prevalence_match.group(1).strip() if prevalence_match else "Unknown"

        st.markdown(f"### {name} – {prevalence}")

        bullet_points = []
        for label in [
            "Lifestyle Summary", "Motivators", "Archetypal Opportunity",
            "3 Personality Traits", "Influenced Groups", "5 Brands They Love"
        ]:
            pattern = rf"{label}\s*:\s*(.+?)(?=\n[A-Z0-9]|$)"
            match = re.search(pattern, persona, re.DOTALL)
            if match:
                value = match.group(1).strip()
                bullet_points.append(f"**{label}:** {value}")

        for bp in bullet_points:
            st.markdown(f"- {bp}")
# ---------- RUN ----------
if st.button("Generate Analysis"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
    if 1 <= len(zip_codes) <= 5:
        search_terms = service_styles + cuisine_styles
        all_competitors = []
        all_latlon = []

        for zip_code in zip_codes:
            lat, lon = get_lat_lon(zip_code)
            if lat and lon:
                all_latlon.append((zip_code, lat, lon))

                if competitor_mode == "Auto via Google Places":
                    nearby_url = (
                        f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?"
                        f"location={lat},{lon}&radius=5000&type=restaurant&keyword={'%20'.join(search_terms)}"
                        f"&key={st.secrets['GOOGLE_API_KEY']}"
                    )
                    response = requests.get(nearby_url)
                    if response.status_code == 200:
                        for place in response.json().get("results", []):
                            service_class = classify_service_style(place)
                            all_competitors.append({
                                "name": place.get("name"),
                                "vicinity": place.get("vicinity", ""),
                                "rating": place.get("rating", ""),
                                "review_count": place.get("user_ratings_total", ""),
                                "website": "",  # placeholder; could be added via details API
                                "service_classification": service_class,
                                "multi_unit": "Likely" if place.get("user_ratings_total", 0) > 100 else "Independent"
                            })

        # Add manual competitors
        for c in manual_competitors:
            all_competitors.append({
                "name": c["name"],
                "vicinity": "Manual Entry",
                "rating": None,
                "review_count": None,
                "website": c["website"],
                "service_classification": "Manual",
                "multi_unit": "Unknown"
            })

        # Filter and deduplicate competitors
        filtered_comps = filter_competitors_by_service_style(all_competitors, service_styles)
        seen = set()
        unique_comps = []
        for comp in filtered_comps:
            if comp["name"] not in seen:
                unique_comps.append(comp)
                seen.add(comp["name"])

        sorted_comps = sorted(
            unique_comps,
            key=lambda x: (x.get("rating", 0) or 0) * (x.get("review_count", 0) or 0),
            reverse=True
        )[:10]

        # --- TABS ---
        tabs = st.tabs(["Patrons", "Competition", "Whitespace"])

        with tabs[0]:
            st.subheader("Patron Personas")
            prompt = build_patron_prompt(zip_codes, user_notes, mode)
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=2500
                )
                render_persona_output(response.choices[0].message.content)
            except Exception as e:
                st.error(f"Error generating personas: {e}")

        with tabs[1]:
            st.subheader("Competitive Landscape")
            st.write(f"Analyzing top {len(sorted_comps)} competitors:")
            for comp in sorted_comps:
                st.markdown(f"### {comp['name']}")
                st.markdown(f"- **Location:** {comp['vicinity']}")
                st.markdown(f"- **Rating:** {comp.get('rating', 'N/A')} ({comp.get('review_count', 0)} reviews)")
                st.markdown(f"- **Service Style:** {comp['service_classification']}")
                st.markdown(f"- **Business Type:** {comp['multi_unit']}")
                if comp.get("website"):
                    st.markdown(f"- **Website:** {comp['website']}")

        with tabs[2]:
            st.subheader("Whitespace Opportunities")
            whitespace_prompt = f"""
            Based on the personas generated and the competitive brand analysis above,
            list 3 whitespace personality trait combinations that are not reflected in the current competitive landscape.
            For each set:
            - Name the 3 personality traits
            - List which Patron Personas would be attracted to them
            - Give a short rationale for why this trio presents a whitespace opportunity.
            """
            try:
                whitespace_response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": whitespace_prompt}],
                    temperature=0.7,
                    max_tokens=800
                )
                st.markdown(whitespace_response.choices[0].message.content)
            except Exception as e:
                st.error(f"Error generating whitespace analysis: {e}")
    else:
        st.warning("Please enter 1 to 5 ZIP codes.")
