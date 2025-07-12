import streamlit as st
import requests
from openai import OpenAI
import time

# ---------- CONFIG ----------
st.set_page_config(page_title="Matador: Local Audience Profiler", layout="centered")

# ---------- OPENAI CLIENT ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- APP HEADER ----------
st.title("🥊 Matador")
st.subheader("Command the Crowd.")
st.write("Enter up to 5 US ZIP codes to generate local audience personas with estimated prevalence and psychographic insight.")

# ---------- INPUT ----------
zip_codes_input = st.text_input("Enter up to 5 ZIP Codes, separated by commas")
user_notes = st.text_area("Add any known local insights, cultural notes, or behaviors (optional)")

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

def get_places_data(lat, lon):
    types = []
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lon}&radius=5000&type=point_of_interest&key={st.secrets['GOOGLE_API_KEY']}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        for result in data.get("results", []):
            for t in result.get("types", []):
                types.append(t)
        unique_types = list(set(types))
        return unique_types[:10]  # Limit for prompt clarity
    return []

def format_structured_data(census, poi_types):
    try:
        total_pop = int(census.get("B01001_001E", 0))
        median_income = int(census.get("B19013_001E", 0))
        white = int(census.get("B02001_002E", 0))
        black = int(census.get("B02001_003E", 0))
        asian = int(census.get("B02001_005E", 0))

        return {
            "Demographics": {
                "Total Population": total_pop,
                "Median Income": f"${median_income:,}",
                "Race Breakdown (%)": {
                    "White": round(white / total_pop * 100, 1),
                    "Black": round(black / total_pop * 100, 1),
                    "Asian": round(asian / total_pop * 100, 1)
                }
            },
            "Nearby Place Types": poi_types,
            "User Notes": user_notes
        }
    except:
        return None

def build_prompt(zip_code, structured_data):
    return f"""
You are a strategic anthropologist and behavioral branding expert.

Based on the following data for ZIP code {zip_code}, identify the top 5 distinct audience personas that exist in the area. Each persona must:

- Have a collective, behaviorally inspired name (e.g., "Sun Chasers", "Concrete Seekers")
- Include a short lifestyle summary (values, habits, motivations, daily behaviors)
- Identify the group's **Archetypal Opportunity** — the type of psychological energy they are drawn to. Choose one from these 12 modified Jungian archetypes: Innocent, Explorer, Sage, Hero, Rebel, Magician, Citizen, Lover, Jester, Caregiver, Creator, Sovereign.
- Include 3 projected personality traits for the group (e.g., curious, intentional, bold)
- Include 3–5 behavioral or emotional motivators
- Include a brief description of 2–3 secondary audience groups they influence
- Estimate a prevalence score (e.g., ~22% of local population)
- Include one sentence of strategic brand opportunity insight

Avoid vague generalizations. Avoid repeating tropes like "they value cultural diversity" unless clearly indicated. Be creative, specific, and behaviorally rich.

Data:
{structured_data}
"""

# ---------- RUN ----------
if st.button("Generate Audience Profiles"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]

    if 1 <= len(zip_codes) <= 5:
        for zip_code in zip_codes:
            with st.spinner(f"Gathering data and building personas for {zip_code}..."):
                census_data = get_census_data(zip_code)
                lat, lon = get_lat_lon(zip_code)
                if lat and lon:
                    poi_types = get_places_data(lat, lon)
                else:
                    poi_types = []

                if census_data:
                    structured_data = format_structured_data(census_data, poi_types)
                    prompt = build_prompt(zip_code, structured_data)

                    try:
                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[
                                {"role": "system", "content": "You are a helpful assistant that generates multiple local psychographic personas for brand strategists."},
                                {"role": "user", "content": prompt}
                            ],
                            temperature=0.85,
                            max_tokens=1800
                        )

                        output = response.choices[0].message.content
                        st.success(f"Top 5 Personas Generated for {zip_code}")
                        st.markdown(output)

                    except Exception as e:
                        st.error(f"OpenAI error for {zip_code}: {e}")

                else:
                    st.error(f"Failed to retrieve Census data for {zip_code}. Try a