import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import os
from datetime import datetime
import plotly.express as px

# Load environment variables
load_dotenv()

# Constants
SPREADSHEET_NAME = 'BROWNS STOCK MANAGEMENT'
SHEET_NAME = 'CHECK_OUT'

# Function to connect to Google Sheets
def connect_to_gsheet(spreadsheet_name, sheet_name):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        credentials = {
            "type": "service_account",
            "project_id": os.getenv("GOOGLE_PROJECT_ID"),
            "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace("\\n", "\n"),
            "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
            "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
            "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
        }
        client_credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
        client = gspread.authorize(client_credentials)
        spreadsheet = client.open(spreadsheet_name)
        return spreadsheet.worksheet(sheet_name)
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return None

# Function to load data from Google Sheets
def load_data_from_google_sheet():
    with st.spinner("Loading data from Google Sheets..."):
        try:
            worksheet = connect_to_gsheet(SPREADSHEET_NAME, SHEET_NAME)
            if worksheet is None:
                return None
            
            data = worksheet.get_all_records()
            if not data:
                st.error("No data found in the Google Sheet.")
                return None

            df = pd.DataFrame(data)
            df.columns = [
                "DATE", "ITEM_SERIAL", "ITEM NAME", "DEPARTMENT", "ISSUED_TO", "QUANTITY",
                "UNIT_OF_MEASURE", "ITEM_CATEGORY", "WEEK", "REFERENCE", "DEPARTMENT_CAT",
                "BATCH NO.", "STORE", "RECEIVED BY"
            ]
            df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
            df["QUANTITY"] = pd.to_numeric(df["QUANTITY"], errors="coerce")
            df.dropna(subset=["QUANTITY"], inplace=True)
            df["QUARTER"] = df["DATE"].dt.to_period("Q")
            current_year = datetime.now().year
            df = df[df["DATE"].dt.year >= current_year - 1]
            return df
        except Exception as e:
            st.error(f"Error loading data: {e}")
            return None

# Cache data for 1 hour
@st.cache_data(ttl=3600)
def get_cached_data():
    return load_data_from_google_sheet()

# Function to calculate proportions
def calculate_proportion(df, identifier, department=None, min_proportion=1.0):
    if df is None:
        return None
    try:
        if identifier.isnumeric():
            filtered_df = df[df["ITEM_SERIAL"].astype(str).str.lower() == identifier.lower()]
        else:
            filtered_df = df[df["ITEM NAME"].str.lower() == identifier.lower()]

        if filtered_df.empty:
            return None

        if department and department != "All Departments":
            filtered_df = filtered_df[filtered_df["DEPARTMENT"] == department]
            if filtered_df.empty:
                return None

        dept_usage = filtered_df.groupby("DEPARTMENT")["QUANTITY"].sum().reset_index()
        total_usage = dept_usage["QUANTITY"].sum()
        if total_usage == 0:
            return None
            
        dept_usage["PROPORTION"] = (dept_usage["QUANTITY"] / total_usage) * 100
        significant_depts = dept_usage[dept_usage["PROPORTION"] >= min_proportion].copy()
        
        if significant_depts.empty and not dept_usage.empty:
            significant_depts = pd.DataFrame([dept_usage.iloc[dept_usage["PROPORTION"].idxmax()]])
        
        total_proportion = significant_depts["PROPORTION"].sum()
        significant_depts["PROPORTION"] = (significant_depts["PROPORTION"] / total_proportion) * 100
        significant_depts["QUANTITY_ABS"] = significant_depts["QUANTITY"].abs()
        significant_depts["INTERNAL_WEIGHT"] = significant_depts["QUANTITY_ABS"] / significant_depts["QUANTITY_ABS"].sum()
        significant_depts.sort_values(by=["PROPORTION"], ascending=[False], inplace=True)
        return significant_depts
    except Exception as e:
        st.error(f"Error calculating proportions: {e}")
        return None

# Function to allocate quantity
def allocate_quantity(df, identifier, available_quantity, department=None):
    proportions = calculate_proportion(df, identifier, department, min_proportion=1.0)
    if proportions is None:
        return None
    
    proportions["ALLOCATED_QUANTITY"] = (proportions["PROPORTION"] / 100 * available_quantity).round(0)
    allocated_sum = proportions["ALLOCATED_QUANTITY"].sum()
    difference = int(available_quantity - allocated_sum)
    
    if difference != 0:
        index_max = proportions["ALLOCATED_QUANTITY"].idxmax()
        proportions.at[index_max, "ALLOCATED_QUANTITY"] += difference
    
    return proportions

# Function to generate historical usage trends
def generate_historical_usage_chart(df, item_name):
    filtered_df = df[df["ITEM NAME"] == item_name]
    if filtered_df.empty:
        return None
    
    fig = px.line(
        filtered_df,
        x="DATE",
        y="QUANTITY",
        title=f"Historical Usage for {item_name}",
        labels={"DATE": "Date", "QUANTITY": "Quantity"},
        markers=True
    )
    return fig

# Streamlit UI
st.set_page_config(
    page_title="SPP Ingredients Management App",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .title {
        text-align: center;
        font-size: 36px;
        font-weight: bold;
        color: #2E86C1;
        font-family: 'Arial', sans-serif;
        margin-bottom: 10px;
    }
    .subtitle {
        text-align: center;
        font-size: 18px;
        color: #6c757d;
        margin-bottom: 30px;
    }
    .footer {
        text-align: center;
        font-size: 12px;
        color: #888888;
        margin-top: 30px;
    }
    .stButton button {
        background-color: #2E86C1;
        color: white;
        font-weight: bold;
        border-radius: 5px;
        padding: 10px 20px;
    }
    .stButton button:hover {
        background-color: #1C6EA4;
    }
    .card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# Main title
st.markdown("<h1 class='title'>SPP Ingredients Management App</h1>", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("<h2 class='title'>Navigation</h2>", unsafe_allow_html=True)
    page = st.radio("Select Page", [
        "Allocation Calculator",
        "Data Overview",
        "Historical Usage",
        "Ingredient Issuance"
    ])

# Load data
if "data" not in st.session_state:
    st.session_state.data = get_cached_data()
data = st.session_state.data

if data is None:
    st.error("Failed to load data from Google Sheets. Please check your connection and credentials.")
    st.stop()

# Extract unique values for filters
unique_item_names = sorted(data["ITEM NAME"].unique().tolist())
unique_departments = sorted(["All Departments"] + data["DEPARTMENT"].unique().tolist())

# Allocation Calculator
if page == "Allocation Calculator":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### Allocation Calculator")
    
    with st.form("allocation_form"):
        num_items = st.number_input("Number of items to allocate", min_value=1, max_value=10, step=1, value=1)
        selected_department = st.selectbox("Filter by Department (optional)", unique_departments)
        
        entries = []
        for i in range(num_items):
            st.markdown(f"**Item {i+1}**")
            col1, col2 = st.columns([2, 1])
            with col1:
                identifier = st.selectbox(f"Select item {i+1}", unique_item_names, key=f"item_{i}")
            with col2:
                available_quantity = st.number_input(f"Quantity:", min_value=0.1, step=0.1, key=f"qty_{i}")

            if identifier and available_quantity > 0:
                entries.append((identifier, available_quantity))

        submitted = st.form_submit_button("Calculate Allocation")
    st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        if not entries:
            st.warning("Please enter at least one valid item and quantity!")
        else:
            for identifier, available_quantity in entries:
                result = allocate_quantity(data, identifier, available_quantity, selected_department)
                if result is not None:
                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    st.markdown(f"<h3 style='color: #2E86C1;'>Allocation for {identifier}</h3>", unsafe_allow_html=True)
                    
                    formatted_result = result[["DEPARTMENT", "PROPORTION", "ALLOCATED_QUANTITY"]].copy()
                    formatted_result = formatted_result.rename(columns={
                        "DEPARTMENT": "Department",
                        "PROPORTION": "Proportion (%)",
                        "ALLOCATED_QUANTITY": "Allocated Quantity"
                    })
                    formatted_result["Proportion (%)"] = formatted_result["Proportion (%)"].round(2)
                    formatted_result["Allocated Quantity"] = formatted_result["Allocated Quantity"].astype(int)
                    
                    st.dataframe(formatted_result, use_container_width=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.error(f"Item {identifier} not found in historical data or has no usage data for the selected department!")

# Data Overview
elif page == "Data Overview":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### Data Overview")
    
    with st.expander("🔍 Advanced Filters", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            min_date = data["DATE"].min().date()
            max_date = data["DATE"].max().date()
            date_range = st.date_input("Select Date Range", [min_date, max_date])
        with col2:
            selected_categories = st.multiselect("Filter by Item Categories", data["ITEM_CATEGORY"].unique().tolist(), default=[])
        
        col3, col4 = st.columns(2)
        with col3:
            selected_items = st.multiselect("Filter by Items", unique_item_names, default=[])
        with col4:
            selected_overview_dept = st.multiselect("Filter by Departments", unique_departments[1:], default=[])
    
    filtered_data = data.copy()
    if date_range:
        filtered_data = filtered_data[(filtered_data["DATE"].dt.date >= date_range[0]) & 
                                     (filtered_data["DATE"].dt.date <= date_range[1])]
    if selected_categories:
        filtered_data = filtered_data[filtered_data["ITEM_CATEGORY"].isin(selected_categories)]
    if selected_items:
        filtered_data = filtered_data[filtered_data["ITEM NAME"].isin(selected_items)]
    if selected_overview_dept:
        filtered_data = filtered_data[filtered_data["DEPARTMENT"].isin(selected_overview_dept)]
    
    st.markdown("#### Filtered Data Preview")
    st.dataframe(filtered_data.head(100), use_container_width=True)
    
    st.markdown("#### Usage Statistics")
    total_usage = filtered_data["QUANTITY"].sum()
    unique_items_count = filtered_data["ITEM NAME"].nunique()
    
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    with stat_col1:
        st.metric("Total Quantity Used", f"{total_usage:,.2f}")
    with stat_col2:
        st.metric("Unique Items", f"{unique_items_count}")
    with stat_col3:
        st.metric("Total Transactions", f"{len(filtered_data):,}")
    
    if not filtered_data.empty:
        st.markdown("#### Department Usage")
        dept_usage = filtered_data.groupby("DEPARTMENT")["QUANTITY"].sum().reset_index()
        dept_usage.sort_values(by="QUANTITY", ascending=False, inplace=True)
        
        fig = px.pie(
            dept_usage, 
            values="QUANTITY", 
            names="DEPARTMENT", 
            title="Usage Distribution by Department",
            hole=0.4
        )
        st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# Historical Usage
elif page == "Historical Usage":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### Historical Usage Trends")
    
    selected_item = st.selectbox("Select Item", unique_item_names)
    chart = generate_historical_usage_chart(data, selected_item)
    
    if chart:
        st.plotly_chart(chart, use_container_width=True)
    else:
        st.warning(f"No historical usage data found for {selected_item}.")
    st.markdown("</div>", unsafe_allow_html=True)

# Ingredient Issuance
elif page == "Ingredient Issuance":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### Ingredient Issuance Console")
    
    with st.form("issuance_form"):
        st.markdown("#### Enter Issuance Details")
        
        # Auto-fill date
        issuance_date = st.date_input("Date", value=datetime.now())
        
        # Item selection
        selected_item = st.selectbox("Item Name", unique_item_names)
        
        # Quantity input
        quantity = st.number_input("Quantity", min_value=0.1, step=0.1)
        
        # Suggestions for other fields
        item_data = data[data["ITEM NAME"] == selected_item].iloc[0]
        department = st.text_input("Department", value=item_data["DEPARTMENT"])
        issued_to = st.text_input("Issued To", value=item_data["ISSUED_TO"])
        unit_of_measure = st.text_input("Unit of Measure", value=item_data["UNIT_OF_MEASURE"])
        item_category = st.text_input("Item Category", value=item_data["ITEM_CATEGORY"])
        reference = st.text_input("Reference", value=item_data["REFERENCE"])
        department_cat = st.text_input("Department Category", value=item_data["DEPARTMENT_CAT"])
        batch_no = st.text_input("Batch No.", value=item_data["BATCH NO."])
        store = st.text_input("Store", value=item_data["STORE"])
        received_by = st.text_input("Received By", value=item_data["RECEIVED BY"])
        
        submitted = st.form_submit_button("Submit Issuance")
    
    if submitted:
        st.success("Issuance recorded successfully!")
    st.markdown("</div>", unsafe_allow_html=True)
