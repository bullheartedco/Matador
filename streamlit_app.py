import streamlit as st
import requests
from openai import OpenAI
import json
from bs4 import BeautifulSoup

# ---------- CONFIG ----------
st.set_page_config(page_title="Matador: Local Audience Profiler", layout="centered")

# ---------- OPENAI CLIENT ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- APP HEADER ----------
st.title("🥊 Matador")
st.subheader("Command the Crowd.")
st.write("Enter up to 5 US ZIP codes to generate local audience personas and analyze competitive restaurant brands.")

# ---------- INPUT ----------
zip_codes_input = st.text_input("Enter up to 5 ZIP Codes, separated by commas")
user_notes = st.text_area("Add any known local insights, cultural notes, or behaviors (optional)")
mode = st.radio("Choose persona generation mode:", ["Cumulative (combined)", "Individual (per ZIP)"])

service_styles = st.multiselect(
    "Select Service Style(s):",
    ["Full Service", "Fast Casual", "Quick Service", "Café"]
)

cuisine_styles = st.multiselect(
    "Select Cuisine Type(s):",
    [
        "Mexican", "Chinese", "Japanese", "Italian", "Thai", "Vietnamese",
        "Indian", "American", "Korean", "Mediterranean", "Seafood",
        "Barbecue", "Vegan", "Vegetarian", "Burgers", "Pizza", "Coffee", "Bakery"
    ]
)

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

def get_places_data(lat, lon, cuisine_styles):
    keyword = "+".join(cuisine_styles)
    nearby_url = (
        f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?"
        f"location={lat},{lon}&radius=5000&type=restaurant&keyword={keyword}"
        f"&key={st.secrets['GOOGLE_API_KEY']}"
    )
    nearby_response = requests.get(nearby_url)
    raw_places = []

    if nearby_response.status_code == 200:
        data = nearby_response.json()
        for result in data.get("results", []):
            rating = result.get("rating", 0)
            review_count = result.get("user_ratings_total", 0)
            score = rating * review_count
            raw_places.append({
                "name": result.get("name"),
                "vicinity": result.get("vicinity"),
                "rating": rating,
                "review_count": review_count,
                "place_id": result.get("place_id"),
                "score": score
            })

    top_places = sorted(raw_places, key=lambda x: x["score"], reverse=True)[:10]
    places = []
    for place in top_places:
        details_url = (
            f"https://maps.googleapis.com/maps/api/place/details/json?"
            f"place_id={place['place_id']}&fields=website&key={st.secrets['GOOGLE_API_KEY']}"
        )
        details_response = requests.get(details_url)
        website = ""
        if details_response.status_code == 200:
            website = details_response.json().get("result", {}).get("website", "")

        places.append({
            "name": place["name"],
            "vicinity": place["vicinity"],
            "rating": place["rating"],
            "review_count": place["review_count"],
            "website": website
        })

    return places

def get_website_text(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    except Exception as e:
        return f"Error fetching website content: {e}"

def analyze_brand_with_gpt(name, address, website_text):
    prompt = f"""
    You are a brand strategist. Based on the following content from the restaurant's website, analyze and return:

    1. The brand’s tone of voice
    2. Three personality traits that reflect the brand
    3. Their core brand message or positioning
    4. What they emphasize in marketing (e.g. ingredients, experience, convenience)
    5. Overall impression in 1 sentence

    Restaurant Name: {name}
    Location: {address}
    Website Text: {website_text[:3000]}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing brand: {e}"

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

def build_patron_prompt(zip_codes, combined_data, mode):
    prompt = "You are a strategic anthropologist and behavioral branding expert.\n\n"
    if mode == "Cumulative (combined)":
        prompt += f"Based on the following cumulative data for ZIP codes {', '.join(zip_codes)}, identify the top 5 most representative audience personas across the region. Each persona must:\n"
    else:
        prompt += f"Generate personas for each individual ZIP code below. For each ZIP, create up to 3 relevant personas.\n"

    prompt += """
- Start with their prevalence score in parentheses (e.g., "(~28%) The Sun Chasers: ...")
- Have a collective, behaviorally inspired name
- Include a short lifestyle summary (values, habits, motivations, daily behaviors)
- Identify the group's **Archetypal Opportunity** — the type of psychological energy they are drawn to (choose from: Innocent, Explorer, Sage, Hero, Rebel, Magician, Citizen, Lover, Jester, Caregiver, Creator, Sovereign)
- Include 3 projected personality traits
- Include 3–5 behavioral or emotional motivators
- Include a brief description of 2–3 secondary audience groups they influence
- Include one sentence of strategic brand opportunity insight
- List the top 5 national brands they are most likely to shop or admire
"""

    if mode == "Cumulative (combined)":
        prompt += "\nOrder all personas from highest to lowest estimated prevalence.\n"
    prompt += f"\nData:\n{json.dumps(combined_data, indent=2)}"
    return prompt

def build_opportunity_prompt(patrons_summary, competitors_summary):
    return f"""
You are a restaurant brand strategist.

Based on the following audience personas and competitor brand personalities:

---

**Patron Personas:**
{patrons_summary}

**Competitor Brands:**
{competitors_summary}

---

Identify three personality traits that represent opportunity whitespace. For each:
- Explain why it’s open
- Link it to specific patron groups that would love it
- Keep it concise and strategic
"""

# ---------- RUN ----------
if st.button("Generate Analysis"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
    if 1 <= len(zip_codes) <= 5:
        combined_data = []
        competitor_list = []
        patrons_output = ""

        for zip_code in zip_codes:
            with st.spinner(f"Collecting data for {zip_code}..."):
                census_data = get_census_data(zip_code)
                lat, lon = get_lat_lon(zip_code)
                poi_types = get_places_data(lat, lon, cuisine_styles) if lat and lon else []

                if census_data:
                    structured = format_structured_data(census_data, [p['name'] for p in poi_types])
                    structured["ZIP Code"] = zip_code
                    combined_data.append(structured)
                    competitor_list.extend(poi_types)
                else:
                    st.error(f"Failed to retrieve Census data for {zip_code}.")

        if combined_data:
            tab1, tab2 = st.tabs(["🧬 Patrons", "🍊 Competition"])

            with tab1:
                with st.spinner("Generating personas..."):
                    prompt = build_patron_prompt(zip_codes, combined_data, mode)
                    try:
                        response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.85,
                            max_tokens=2000
                        )
                        patrons_output = response.choices[0].message.content
                        st.markdown(patrons_output)
                    except Exception as e:
                        st.error(f"OpenAI error: {e}")

            with tab2:
                st.markdown("### Top 10 Competitor Restaurants")
                competitors_summary = ""
                for r in competitor_list:
                    competitors_summary += f"- {r['name']} at {r['vicinity']}\n"
                    st.markdown(f"**{r['name']}** — {r['vicinity']}")
                    st.markdown(f"""
- **Google Rating:** ⭐ {r.get("rating", "N/A")} ({r.get("review_count", "0")} reviews)
""")
                    if r.get("website"):
                        website_text = get_website_text(r['website'])
                        brand_analysis = analyze_brand_with_gpt(r['name'], r['vicinity'], website_text)
                        st.markdown(brand_analysis)
                    else:
                        st.markdown("_No website provided for analysis._")

                if patrons_output and competitors_summary:
                    st.markdown("### 🌟 Opportunity Personality Traits")
                    opp_prompt = build_opportunity_prompt(patrons_output, competitors_summary)
                    try:
                        opp_response = client.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=[{"role": "user", "content": opp_prompt}],
                            temperature=0.85,
                            max_tokens=1000
                        )
                        st.markdown(opp_response.choices[0].message.content)
                    except Exception as e:
                        st.error(f"OpenAI error: {e}")
    else:
        st.warning("Please enter between 1 and 5 ZIP codes, separated by commas.")
