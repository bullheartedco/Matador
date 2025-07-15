import streamlit as st
import requests
from openai import OpenAI
from bs4 import BeautifulSoup
from supabase import create_client, Client
import stripe
import json
import time

# ---------- CONFIG ----------
st.set_page_config(page_title="Matador: Patron, Competition, Whitespace Strategy", layout="wide")

# ---------- SECRETS ----------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
STRIPE_API_KEY = st.secrets["STRIPE_API_KEY"]
STRIPE_PRODUCT_PRICE_ID = st.secrets["STRIPE_PRODUCT_PRICE_ID"]
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- CLIENTS ----------
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
stripe.api_key = STRIPE_API_KEY

# Google-Aligned Service Styles (defined here for global access)
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

# ---------- HELPER FUNCTIONS ----------
def get_user():
    return st.session_state.get("user")

def count_user_reports(user_id):
    response = supabase.table("reports").select("id").eq("user_id", user_id).execute()
    return len(response.data)

def save_report(user_id, data):
    report_data = {
        "user_id": user_id,
        "zip_codes": json.dumps(data["zip_codes"]),
        "user_notes": data["user_notes"],
        "service_styles": json.dumps(data["service_styles"]),
        "cuisine_types": json.dumps(data["cuisine_types"]),
        "competitor_mode": data["competitor_mode"],
        "manual_competitors": json.dumps(data["manual_competitors"]),
        "personas": data["personas"],
        "competitors": data["competitors"],
        "whitespace": data["whitespace"],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    supabase.table("reports").insert(report_data).execute()

def fetch_census_for_zips(zip_codes):
    rows = []
    for zip_code in zip_codes:
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
                rows.append(dict(zip(data[0], data[1])))
    return rows

def get_lat_lon(zip_code):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={st.secrets['GOOGLE_API_KEY']}"
    response = requests.get(url)
    if response.status_code == 200 and response.json().get("results"):
        location = response.json()["results"][0]["geometry"]["location"]
        return location["lat"], location["lng"]
    return None, None

def get_places_data(lat, lon, search_terms):
    keyword = "+".join(search_terms)
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
        website = details_response.json().get("result", {}).get("website", "") if details_response.status_code == 200 else ""
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
    except:
        return "Unable to fetch website content."

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
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500
    )
    return response.choices[0].message.content

def build_patron_prompt(zip_codes, user_notes, mode):
    if mode == "Cumulative (combined)":
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
    else:
        prompt = ""
        for z in zip_codes:
            prompt += f"""
For ZIP code {z}, generate:
- 1–2 audience personas with:
  1. Persona Name (collective, not individual)
  2. Lifestyle and cultural summary
  3. Archetype attraction
  4. Motivators
  5. Influenced secondary groups
  6. 5 brands they love
  7. Prevalence estimate
User Notes: {user_notes}
"""
        return f"You are an expert in psychographics, anthropology, and brand strategy.\nBelow are prompts for each ZIP code. Answer each separately.\n{prompt}"

def generate_report(zip_codes, user_notes, mode, service_styles, cuisine_styles, competitor_mode, manual_competitors):
    census_data = fetch_census_for_zips(zip_codes)
    demographic_summary = ""
    if census_data:
        for entry in census_data:
            demographic_summary += f"- {entry['NAME']}: Population {entry.get('B01001_001E', 'N/A')}, "
            demographic_summary += f"Median Income ${entry.get('B19013_001E', 'N/A')}, "
            demographic_summary += f"White %: {entry.get('B02001_002E', 'N/A')}, "
            demographic_summary += f"Black %: {entry.get('B02001_003E', 'N/A')}, "
            demographic_summary += f"Asian %: {entry.get('B02001_005E', 'N/A')}\n"
    else:
        demographic_summary = "No Census data available."
    
    full_prompt = (
        "Use this Census data ethically and sensitively to guide audience personas for restaurant brand strategy. "
        f"Demographic Snapshot:\n{demographic_summary}\n\n" + build_patron_prompt(zip_codes, user_notes, mode)
    )
    personas_response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": full_prompt}],
        temperature=0.75,
        max_tokens=1600
    )
    personas = personas_response.choices[0].message.content

    search_terms = []
    for style in service_styles:
        search_terms += service_style_map.get(style, [])
    search_terms += cuisine_styles

    competitors_list = []
    if competitor_mode == "Auto via Google Places":
        for zip_code in zip_codes:
            lat, lon = get_lat_lon(zip_code)
            if lat and lon:
                competitors_list.extend(get_places_data(lat, lon, search_terms))
    else:
        competitors_list.extend(manual_competitors)
    
    seen = set()
    unique_competitors = []
    for c in competitors_list:
        if c["name"] not in seen:
            website_text = get_website_text(c["website"]) if c.get("website") else ""
            analysis = analyze_brand_with_gpt(c["name"], c.get("vicinity", ""), website_text) if website_text else "No website analysis available."
            unique_competitors.append(f"### {c['name']}\n**Location:** {c.get('vicinity', 'Manual Entry')}\n**Rating:** {c.get('rating', 'N/A')} ({c.get('review_count', '0')} reviews)\n**Website:** {c.get('website', 'N/A')}\n{analysis}")
            seen.add(c["name"])
    competitors = "\n\n".join(unique_competitors[:10])

    whitespace_prompt = f"""
    Based on the patron personas below, identify three whitespace brand personality opportunities that aren't currently dominant.
    For each opportunity:
    - List 3 underrepresented brand personality traits
    - Name 2–3 patron personas who would likely be attracted
    - Write a short brand strategy insight on how a new brand could embody this
    Patron Personas:\n{personas}
    """
    whitespace_response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": whitespace_prompt}],
        temperature=0.75,
        max_tokens=1000
    )
    whitespace = whitespace_response.choices[0].message.content

    return {"zip_codes": zip_codes, "user_notes": user_notes, "service_styles": service_styles, "cuisine_types": cuisine_styles,
            "competitor_mode": competitor_mode, "manual_competitors": manual_competitors, "personas": personas, "competitors": competitors, "whitespace": whitespace}

# ---------- AUTHENTICATION ----------
if "user" not in st.session_state:
    st.session_state.user = None
if "mode" not in st.session_state:
    st.session_state.mode = "login"
if "is_vip" not in st.session_state:
    st.session_state.is_vip = False

def fetch_is_vip(user_id):
    response = supabase.table("users").select("is_vip").eq("id", user_id).execute()
    if response.data:
        return response.data[0]["is_vip"]
    return False

if st.session_state.mode == "login":
    st.title("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.user = response.user
            st.session_state.is_vip = fetch_is_vip(response.user.id)
            st.session_state.mode = "input"
            st.rerun()
        except Exception as e:
            st.error(f"Login failed: {e}")
    if st.button("Register"):
        st.session_state.mode = "register"
        st.rerun()

elif st.session_state.mode == "register":
    st.title("Register")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Register"):
        try:
            response = supabase.auth.sign_up({"email": email, "password": password})
<<<<<<< HEAD
            if response.session:  # Only if immediate session (confirmation disabled)
                supabase.auth.set_session(response.session.access_token, response.session.refresh_token)
=======
            if response.user:
>>>>>>> 24407fcc22a1a0177184646481f760d3903f74e4
                supabase.table("users").insert({
                    "id": response.user.id,
                    "email": email,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "is_vip": False
                }).execute()
                st.success("Registration successful! Please log in.")
                st.session_state.mode = "login"
                st.rerun()
            else:
                st.warning("Check your email to confirm registration.")
        except Exception as e:
            st.error(f"Registration failed: {e}")
    if st.button("Back to Login"):
        st.session_state.mode = "login"
        st.rerun()

else:
    user = get_user()
    if not user:
        st.session_state.mode = "login"
        st.rerun()
    else:
        st.sidebar.title("Navigation")
        page = st.sidebar.radio("Go to", ["Generate Report", "My Reports"])

        if page == "Generate Report":
            st.title("💃🏻 Matador")
            st.subheader("Command the Crowd.")
            st.write("Enter up to 5 US ZIP codes to generate local audience personas and analyze competitive restaurant brands.")
            st.info("Enter a promo code at checkout for discounts on this report (e.g., 20% off).")

            zip_codes_input = st.text_input("Enter up to 5 ZIP Codes, separated by commas")
            user_notes = st.text_area("Add any known local insights, cultural notes, or behaviors (optional)")
            mode = st.radio("Choose persona generation mode:", ["Cumulative (combined)", "Individual (per ZIP)"])
            selected_service_styles = st.multiselect(
                "Select Service Style(s):",
                options=list(service_style_map.keys())
            )
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

            if st.button("Generate Report"):
                zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
                if 1 <= len(zip_codes) <= 5:
                    user_reports = count_user_reports(user.id)
                    if user_reports < 3 or st.session_state.is_vip:
                        with st.spinner("Generating report..."):
                            report_data = generate_report(zip_codes, user_notes, mode, selected_service_styles, cuisine_styles, competitor_mode, manual_competitors)
                            save_report(user.id, report_data)
                            st.session_state.report_data = report_data
                            st.session_state.mode = "report"
                            st.rerun()
                    else:
                        # Persist inputs for post-payment generation
                        st.session_state.pending_zip_codes = zip_codes
                        st.session_state.pending_user_notes = user_notes
                        st.session_state.pending_mode = mode
                        st.session_state.pending_service_styles = selected_service_styles
                        st.session_state.pending_cuisine_styles = cuisine_styles
                        st.session_state.pending_competitor_mode = competitor_mode
                        st.session_state.pending_manual_competitors = manual_competitors
                        session = stripe.checkout.Session.create(
                            payment_method_types=["card"],
                            line_items=[{"price": STRIPE_PRODUCT_PRICE_ID, "quantity": 1}],
                            mode="payment",
                            allow_promotion_codes=True,
                            success_url=f"{st.get_option('browser.serverAddress')}?session_id={{CHECKOUT_SESSION_ID}}",
                            cancel_url=st.get_option("browser.serverAddress")
                        )
                        st.write(f'<script>window.location.href = "{session.url}";</script>', unsafe_allow_html=True)
                else:
                    st.warning("Please enter between 1 and 5 ZIP codes.")

        elif page == "My Reports":
            st.title("My Reports")
            reports = supabase.table("reports").select("*").eq("user_id", user.id).order("generated_at", desc=True).execute()
            for report in reports.data:
                st.write(f"**Generated on:** {report['generated_at']} | **ZIP Codes:** {json.loads(report['zip_codes'])}")
                if st.button(f"View Report {report['id']}"):
                    st.session_state.report_data = {
                        "personas": report["personas"],
                        "competitors": report["competitors"],
                        "whitespace": report["whitespace"]
                    }
                    st.session_state.mode = "report"
                    st.rerun()

        if st.session_state.mode == "report":
            st.title("Report")
            tabs = st.tabs(["Patrons", "Competition", "White Space"])
            with tabs[0]:
                st.markdown(st.session_state.report_data["personas"])
            with tabs[1]:
                st.markdown(st.session_state.report_data["competitors"])
            with tabs[2]:
                st.markdown(st.session_state.report_data["whitespace"])
            if st.button("Back"):
                st.session_state.mode = "input"
                st.rerun()

        query_params = st.query_params
        if "session_id" in query_params:
            session_id = query_params["session_id"]
            session = stripe.checkout.Session.retrieve(session_id)
            if session.payment_status == "paid":
                # Retrieve persisted inputs
                zip_codes = st.session_state.get("pending_zip_codes", [])
                user_notes = st.session_state.get("pending_user_notes", "")
                mode = st.session_state.get("pending_mode", "Cumulative (combined)")
                selected_service_styles = st.session_state.get("pending_service_styles", [])
                cuisine_styles = st.session_state.get("pending_cuisine_styles", [])
                competitor_mode = st.session_state.get("pending_competitor_mode", "Auto via Google Places")
                manual_competitors = st.session_state.get("pending_manual_competitors", [])
                with st.spinner("Generating report after payment..."):
                    report_data = generate_report(zip_codes, user_notes, mode, selected_service_styles, cuisine_styles, competitor_mode, manual_competitors)
                    save_report(user.id, report_data)
                    st.session_state.report_data = report_data
                    st.session_state.mode = "report"
                    # Clear pending data
                    for key in ["pending_zip_codes", "pending_user_notes", "pending_mode", "pending_service_styles", "pending_cuisine_styles", "pending_competitor_mode", "pending_manual_competitors"]:
                        if key in st.session_state:
                            del st.session_state[key]
                    st.rerun()
            else:
                st.error("Payment failed or was canceled.")
                st.session_state.mode = "input"
<<<<<<< HEAD
                st.rerun()
=======
                st.rerun()
>>>>>>> 24407fcc22a1a0177184646481f760d3903f74e4
