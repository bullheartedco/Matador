import streamlit as st
import requests
from openai import OpenAI

# ---------- CONFIG ----------
st.set_page_config(page_title="Matador: Local Audience Profiler", layout="centered")

# ---------- OPENAI CLIENT ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- APP HEADER ----------
st.title("🥊 Matador")
st.subheader("Command the Crowd.")
st.write("Enter a ZIP code to generate a local audience profile using U.S. Census data and AI-powered psychographic insights.")

# ---------- INPUT ----------
zip_code = st.text_input("Enter a US ZIP Code", max_chars=10)
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

def format_structured_data(census):
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
            "Behavior Patterns": [
                "Frequent visits to parks, cafes, and community events",
                "Likely use of public transportation or rideshares",
                "Interest in local businesses and arts scenes"
            ],
            "Values & Interests": [
                "Cultural diversity", "Community belonging", "Support for local makers",
                "Affordable lifestyle with social engagement"
            ],
            "User Notes": user_notes
        }
    except:
        return None

def build_prompt(zip_code, structured_data):
    return f"""
You are an expert in psychographics, anthropology, and brand strategy.

Based on the following data for ZIP code {zip_code}, generate:
1. A primary audience persona (name and description)
2. A personality archetype (Citizen, Sage, Rebel, Lover, Hero, Explorer, Creator, Jester, Caregiver, Innocent, Sovereign, Magician)
3. Top 3-5 behavioral motivators
4. 2–3 influenced secondary groups
5. A local brand opportunity insight

Data:
{structured_data}
"""

# ---------- RUN ----------
if st.button("Generate Audience Profile"):
    if zip_code:
        with st.spinner("Gathering data and building persona..."):
            census_data = get_census_data(zip_code)
            if census_data:
                structured_data = format_structured_data(census_data)
                prompt = build_prompt(zip_code, structured_data)

                try:
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that generates local psychographic personas for brand strategists."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.8,
                        max_tokens=900
                    )

                    output = response.choices[0].message.content
                    st.success("Profile Generated")
                    st.markdown(output)

                except Exception as e:
                    st.error(f"OpenAI error: {e}")

            else:
                st.error("Failed to retrieve Census data. Try a different ZIP code.")
    else:
        st.warning("Please enter a ZIP code.")
