import streamlit as st

st.title("Matador")
st.write(
    "Matador is a psychographic profiling tool for brand strategists. Enter a ZIP code to generate an AI-driven audience persona using U.S. Census data and natural language insights powered by GPT-4."
)
import streamlit as st
import requests
import openai

# ---------- CONFIG ----------
st.set_page_config(page_title="Matador: Local Audience Profiler", layout="centered")
openai.api_key = st.secrets["OPENAI_API_KEY"]  # Store in .streamlit/secrets.toml

# ---------- APP HEADER ----------
st.title("🤺 Matador")
st.subheader("Command the Crowd.")
st.write("Enter a ZIP code to generate a local audience profile using free public data and AI-driven psychographic insights.")

# ---------- INPUT ----------
zip_code = st.text_input("Enter a US ZIP Code", max_chars=10)
user_notes = st.text_area("Add any known local insights, cultural notes, or behaviors (optional)")

# ---------- API HELPERS ----------
def get_census_data(zip_code):
    # Using the ACS 5-Year Data for 2021 which supports ZIP Code Tabulation Areas
    url = "https://api.census.gov/data/2021/acs/acs5"
    params = {
        "get": "NAME,B01001_001E,B19013_001E,B02001_002E,B02001_003E,B02001_005E",
        "for": f"zip code tabulation area:{zip_code}",
        "key": st.secrets["CENSUS_API_KEY"]  # Add your key to Streamlit Secrets
    }
    
    response = requests.get(url, params=params)

    # Debug print
    st.write("Census API URL:", response.url)
    st.write("Status Code:", response.status_code)
    st.write("Raw Response:", response.text)

    if response.status_code == 200:
        data = response.json()
        if len(data) > 1:
            labels = data[0]
            values = data[1]
            return dict(zip(labels, values))
    return None

def format_structured_data(census):
    try:
        total_pop = int(census.get("P1_001N", "0"))
        white = int(census.get("P2_005N", "0"))
        black = int(census.get("P2_006N", "0"))
        asian = int(census.get("P2_007N", "0"))

        return {
            "Demographics": {
                "Total Population": total_pop,
                "Race Breakdown": {
                    "White (%)": round(white / total_pop * 100, 1),
                    "Black (%)": round(black / total_pop * 100, 1),
                    "Asian (%)": round(asian / total_pop * 100, 1)
                },
                "Note": "Limited to basic race data from Census. Other behavior patterns inferred."
            },
            "Behavior Patterns": [
                "Frequent visits to parks, cafés, and local eateries",
                "Interest in community events and shared cultural activities",
                "Likely to use public transit or ride-sharing"
            ],
            "Values & Interests": [
                "Cultural diversity", "Belonging", "Support for local business", "Accessible lifestyle"
            ],
            "User Notes": user_notes
        }
    except:
        return None

# ---------- GPT PROMPT ----------
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

                # GPT Call
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.8,
                    max_tokens=900
                )
                st.success("Profile Generated")
                st.markdown(response["choices"][0]["message"]["content"])
            else:
                st.error("Failed to retrieve Census data. Try a different ZIP code.")
    else:
        st.warning("Please enter a ZIP code.")