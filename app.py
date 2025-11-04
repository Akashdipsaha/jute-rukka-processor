import streamlit as st
import google.generativeai as genai
import pandas as pd
from PIL import Image
import json
import re
import io
from fpdf import FPDF # New import for PDF creation
import pymongo # New import for MongoDB
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from urllib.parse import quote_plus # New import to fix connection string error
import fitz  # --- NEW IMPORT FOR PDFS ---

import warnings
try:
    from cryptography.utils import CryptographyDeprecationWarning
    # Suppress only this specific warning from PyMongo
    warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
except ImportError:
    pass 


MY_API_KEY = "AIzaSyCWeRY8cV44-V9cLrhj0oBi9KhKym7YvKk" 

MONGO_USER = "Akashdip_Saha"
MONGO_PASSWORD = "STIL@12345"
MONGO_CLUSTER_URL = "cluster0.2zgbica.mongodb.net/"


st.set_page_config(
    page_title="🤖 Raw Jute Rukka Processor",
    page_icon="📄",
    layout="wide"
)


if 'reset_counter' not in st.session_state:
    st.session_state.reset_counter = 0

# 'camera_open' is a "gate" to control the camera button logic.
if 'camera_open' not in st.session_state:
    st.session_state.camera_open = False 

# 'active_input' tracks which input (upload or camera) was used last.
if 'active_input' not in st.session_state:
    st.session_state.active_input = None

# --- NEW STATE FOR PAGINATED EDITING ---
# 'extraction_done' is a flag to show the edit/download UI.
if 'extraction_done' not in st.session_state:
    st.session_state.extraction_done = False

# 'result_list' holds the list of extracted JSON objects (as Python dicts).
# This is now our "single source of truth" for the data.
if 'result_list' not in st.session_state:
    st.session_state.result_list = []

# 'current_edit_index' tracks which Rukka we are currently viewing/editing.
if 'current_edit_index' not in st.session_state:
    st.session_state.current_edit_index = 0
    
# 'individual_json_editor' holds the text for the *current* item being edited.
# This is the key to fixing the pagination bug.
if 'individual_json_editor' not in st.session_state:
    st.session_state.individual_json_editor = ""
# --- END NEW STATE ---


# --- Helper Functions ---
# These functions do the "heavy lifting" (PDF/TXT creation, AI calls).

def create_pdf(json_text):
    """
    Creates a structured, report-style PDF from a JSON string.
    This function now handles a LIST of Rukkas.
    """
    # Initialize the PDF object
    pdf = FPDF()
    pdf.add_page()
    
    # Edge Case: Handle empty or invalid JSON text
    if not json_text or json_text.strip() == "[]":
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, 'No Rukka data to generate PDF.', 0, 1, 'C')
        # Return the PDF data as a byte string
        return pdf.output(dest='S').encode('latin-1')
        
    try:
        # Load the JSON string into a Python LIST of dictionaries
        data_list = json.loads(json_text)
        
        # --- BATCH PROCESSING UPDATE ---
        # Ensure data is a list for the loop
        if not isinstance(data_list, list):
            data_list = [data_list] # Make it a list of one

        # Loop through each Rukka document in the JSON array
        for i, data_dict in enumerate(data_list):
            if i > 0:
                pdf.add_page() # Add a new page for each new Rukka
            
            # Add a main title for this document
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, f'Extracted Rukka Data (Document {i+1})', 0, 1, 'C')
            pdf.ln(5) # Add a 5mm line break
            
            try:
                df = pd.json_normalize(data_dict)
                flat_dict = df.to_dict(orient='records')[0]
            except Exception:
                st.warning(f"Rukka {i+1} JSON structure is complex. PDF will show raw data.")
                flat_dict = {"RawData": json.dumps(data_dict, indent=2)}

            # Set a monospaced font for the data part for good alignment
            pdf.set_font("Courier", size=10)
            
            for key, value in flat_dict.items():
                # Only print rows that actually have data
                if value is not None and str(value).strip() != "":
                    # Format the key: 'items_0_name' -> 'Items 0 Name'
                    key_name = str(key).replace('_', ' ').title()
                    
                    # Print the Key in Bold
                    pdf.set_font("Courier", 'B', 10)
                    pdf.multi_cell(0, 5, f"{key_name}:")
                    
                    # Print the Value in regular font, indented
                    pdf.set_font("Courier", '', 10)
                    pdf.multi_cell(0, 5, f"  {str(value)}")
                    
                    # Add a small spacer
                    pdf.ln(2)
    
    except Exception as e:
        # Final fallback: If *anything* fails, just dump the raw text.
        print(f"Could not convert JSON to table for PDF, falling back. Error: {e}")
        pdf.set_font("Arial", size=10)
        # We must encode/decode to handle potential non-Latin characters
        pdf.multi_cell(0, 5, json_text.encode('latin-1', 'replace').decode('latin-1'))
    
    # Return the PDF data as a byte string
    return pdf.output(dest='S').encode('latin-1')

def create_text_report(json_text):
    """
    Creates a structured, report-style TXT file from a JSON string.
    This function now handles a LIST of Rukkas.
    """
    report_string = ""
    
    # Edge Case: Handle empty or invalid JSON text
    if not json_text or json_text.strip() == "[]":
        return "No Rukka data to generate text report."
        
    try:
        data_list = json.loads(json_text)
        
        # --- BATCH PROCESSING UPDATE ---
        if not isinstance(data_list, list):
            data_list = [data_list]

        # Loop through each Rukka document
        for i, data_dict in enumerate(data_list):
            # Add a title
            report_string += f"Extracted Rukka Data (Document {i+1})\n"
            report_string += "=================================\n\n"
            
            try:
                df = pd.json_normalize(data_dict)
                flat_dict = df.to_dict(orient='records')[0]
            except Exception:
                st.warning(f"Rukka {i+1} JSON structure is complex. TXT will show raw data.")
                flat_dict = {"RawData": json.dumps(data_dict, indent=2)}

            # Loop through key/value pairs and format them
            for key, value in flat_dict.items():
                if value is not None and str(value).strip() != "":
                    key_name = str(key).replace('_', ' ').title()
                    report_string += f"{key_name}:\n"
                    report_string += f"  {str(value)}\n\n" # Add spacer
            
            report_string += "\n\n" # Add space between documents
    
    except Exception as e:
        # Final fallback: just return the raw text
        print(f"Could not convert JSON to table for TXT, falling back. Error: {e}")
        report_string = json_text
    
    return report_string

# --- *** THIS IS THE FIX *** ---
# 1. The function now accepts 'image_bytes' (which are hashable)
@st.cache_data(show_spinner=False)
def get_json_from_image(image_bytes, api_key): 
    """
    Sends the image and a specialized prompt to the Gemini API.
    This is "Worker 1": The Transcriber.
    It returns only the extracted JSON text.
    
    --- UPDATED ---
    This function now expects raw image BYTES and opens the
    image *inside* the function to be compatible with st.cache_data.
    """
    
    try:
        # 2. Open the image *inside* the function from the bytes
        img = Image.open(io.BytesIO(image_bytes))

        # Configure the generative AI library with the API key
        genai.configure(api_key=api_key)
        
        # Use the correct, full model name
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025') 
        
        # --- *** MASSIVELY UPDATED PROMPT *** ---
        # This is the new "super-prompt" as you requested.
        # It is highly specialized for "Rukkas" and includes the
        # Area/Mukam mapping data you provided.
        prompt_text = """
You are a specialized Data Extraction Engine. Your SOLE purpose is to analyze images of "Raw Jute Purchase Slips" (also known as "Rukkas") and convert them into a structured JSON object.

**PRIMARY DIRECTIVE:**
Absolute accuracy is mandatory. Pay meticulous attention to handwritten text, especially numbers (weights, rates, bales, PO No.), dates, and names.

**AREA/MUKAM REFERENCE LIST:**
This is your single source of truth for location names. You MUST use this list to correct messy handwriting or abbreviations.
* **Intelligent Correction:** If you see a handwritten value like "K'pur", "Karimpr", or "Karinpur", you MUST correct it to `"mukam": "Karimpur"`. If you see "Kishang" or "Kishanganj (A)", you MUST correct it to `"mukam": "Kishanganj"`. If you see a name not on this list (e.g., "Rejinagar"), use your best judgment to spell it correctly.
* **Area/Mukam Linking:** When you identify a `mukam`, you MUST use this list to find its corresponding `area`. The `area` field you extract (e.g., "SOUTH BENGAL", "BIHAR") MUST be the one associated with that `mukam` in the list.

* **SOUTH BENGAL:** PATKIBARI, JALANGI, BETHUADAHARI, BANGALIHI, NABADWIP, SAGARPARA, SAHEBNAGAR, GOLABARI, KRISHNANAGAR, NAZIRPUR, SINGUR, BADURIA, KANTALIA, BHIMPUR, HARIPAL, KALITALA, ISLAMPUR-SB, NIMTALA, CHAPRA, MOYNA, COSSIMBAZAR, GOAS, MAJDIA, BONGAON, BEHRAMPUR, KANTHALIA-L, PALASIPARA-L, NILGANJ-L, PALASIPARA, ASSANAGAR, KARIMPUR, TRIMOHINI, DHUBULIA, KATWA, CHAPRA-L, REZINAGAR, AMTALA-L, KALITALA-L, AMTALA, SEORAPHULLY, GOPALNAGAR, NALIKUL, ASSANNAGR-L, DEBNATHPUR, RANAGHAT-HB, BARA ANDULIA, MARUTHIA, JIAGANG, BETAI, MURUTHIA, BIRPUR, ANDULIA-L, ANDULIA, BHIMPUR-HB, CHAKDAH, KALNA, KALIGANJ, ARANGHATA, DAINHAT, BURDWAN-L, DOMKAL, LALBAGH, PALSHIPARA-L, BERACHAPA, BHAGIRATHPUR, JANGIPUR, HARINGHATA-L, BETHUADAHARI-L, RANAGhat, MAYAPUR, GOLABARI, HARIPAL, TARKESWAR, RAJAPUR, CHAPADANGA
* **BIHAR:** PURNEA, FORBESGANJ, KISHANGANJ, KISHANGANJ-A, KISHANGANJ-J, KISHANGANJ-B, GULABBAGH
* **ASSAM:** TARABARI, BILASIPARA, GUWAHATI, GOSSAIGAON, KHARUPETIA, NOWGAON, DHUBRI, BHURAGAON, DHINGBAZAR
* **SEMI NORTHERN:** SAMSI-J, MALDAH, SRIGHAR, GANGARAMPUR-L, TULSIHATA, HARISHCHPORE, RAIGANJ, KANKI, BULBULCHANDI, GAZOLE-L, KANKI-L, ISLAMPUR-SN, BALURGHAT-L
* **NORTHERN:** DINHATA, MAYNAGURI, BAXIRHAT, HUSLUDANGA, BASIRHAT, BELAKOBA, DHUPGURI, HALDIBARI, BAMANHAT, TOOFANGANJ, MATHABHANGA, COOCHBEHAR, CHOWDHURIHAT, DEWANHAT, BAROBISHA
* **ODISHA:** BHADRAK
* **BANGLADESH:** BANGLADESH

**EXTRACTION & FORMATTING RULES:**
1.  **Analyze Image:** Scan the entire document for all fields.
2.  **Field Mapping:** Extract the following fields. If a field is empty or just a dash, omit it from the JSON (do not use `null` or `""`).
    * `document_type`: (e.g., "P.O. REQUIRED SLIP", "RAW JUTE PURCHASE CLOSING SLIP")
    * `po_slip_no`: The main slip number (e.g., "No. 578", "No. 1223"). Extract as a **number**.
    * `date`: The main document date. Standardize to `YYYY-MM-DD`.
    * `mill_name`: (e.g., "STIL / UNIT : HASTINGS MILL", "SHAKTIGARH TEXTILE & INDUSTRIES LTD.")
    * `po_no`: The Purchase Order number. Extract as a **number** (e.g., 848, 363).
    * `po_date`: Standardize to `YYYY-MM-DD`.
    * `mr_no`: Extract as a **number**.
    * `mr_date`: Standardize to `YYYY-MM-DD`.
    * `g_srl_no`: Extract as a **number**.
    * `g_srl_date`: Standardize to `YYYY-MM-DD`.
    * `broker`: The full name of the broker (e.g., "Surojmal Ramprasad", "Tolia'swar Enterprises").
    * `lorry_arrived_on`: Standardize to `YYYY-MM-DD`.
    * `area`: The checked/written area. This MUST be one of the main areas from the REFERENCE LIST (e.g., "SOUTH BENGAL", "BIHAR").
    * `mukam` (or `agency_mukam`): The handwritten location. Use the REFERENCE LIST to correct spelling and output the clean name (e.g., "Karimpur").
    * `bales_mark`: (e.g., "SM", "RR / CS", "SR / MORA").
    * `no_of_lorry`: (e.g., "01(X) 100 QTLS / PER LORRY").
    * `items`: This is the main table. This **must** be a JSON array of objects. Extract `grade`, `bales`, `quantity`, and `rate` (Per Qtls) for each row.
    * `total_weight`: Extract as a **number**.
    * `total_bales`: Extract as a **number**.
    * `remarks`: (e.g., "SKT-358 ...", "(+) 50/- premium...").
    * `payment_terms`: (e.g., "60 Days").
3.  **Data Typing:**
    * **Numbers:** `po_slip_no`, `po_no`, `mr_no`, `g_srl_no`, `bales`, `total_bales`, `total_weight`, `quantity`, and `rate` **must** be JSON numbers (e.g., `85.00`, `622730`), not strings. Remove any "/-" symbols from rates.
    * **Dates:** All dates **must** be `YYYY-MM-DD` format.
    * **Strings:** All other values must be strings.
4.  **Table Handling:** The `items` array must contain one object for each row, even if the row is empty or just has a grade.

**OUTPUT:**
* You **must** return **ONLY** a single, valid, human-readable JSON object.
* The JSON **must** be "pretty-printed" with standard indentation (e.g., 2 spaces) and line breaks.
* Do not include *any* introductory text, explanations, or markdown formatting (like ```json). Your entire response must be the JSON object itself.
"""
        # --- *** END OF UPDATED PROMPT *** ---
        
        # 3. Send the PIL Image object 'img' to the model
        response = model.generate_content([prompt_text, img])
        ai_response_text = response.text

        start_index = ai_response_text.find('{')
        end_index = ai_response_text.rfind('}')
        
        if start_index != -1 and end_index != -1:
            clean_json_text = ai_response_text[start_index : end_index + 1]
            json.loads(clean_json_text) # Validate that it's good JSON
            return clean_json_text
        else:
            # If no JSON object is found
            return None # Return None to signal failure
        
    except Exception as e:
        # Handle all other errors, especially API key issues
        if "API Key not valid" in str(e):
            st.error("🚨 CRITICAL ERROR: The Google AI API Key is invalid or expired. Please check your secrets file.")
        else:
            st.error(f"An error occurred during AI processing: {e}")
        return None

def save_to_mongodb(username, password, cluster_url, json_text):
    """
    Connects to MongoDB and inserts the JSON data.
    Includes robust error handling.
    """
    
    # Edge Case: Don't save empty data
    if not json_text or json_text.strip() == "[]":
        return False, "Cannot save. The extracted data is empty."
        
    try:
        # Escape the username and password for the connection string
        escaped_user = quote_plus(username)
        escaped_pass = quote_plus(password)
        
        # Build the new, safe connection string
        connection_string = f"mongodb+srv://{escaped_user}:{escaped_pass}@{cluster_url}"
        
        # Create a new client and connect to the server
        client = MongoClient(connection_string, server_api=ServerApi('1'))
        
        # Send a ping to confirm a successful connection (optional but good)
        client.admin.command('ping')
        
        # Select your database and collection
        db = client["rukka_project"] # UPDATED: Rukka-specific DB
        collection = db["rukka_extractions"] # UPDATED: Rukka-specific collection
        
        # --- BATCH PROCESSING UPDATE ---
        # Convert the JSON text string into a Python LIST of dictionaries
        data_list = json.loads(json_text)
        
        # Ensure data is a list
        if not isinstance(data_list, list):
            data_list = [data_list] # Make it a list of one if it's a single object
        
        # This is the line that inserts EACH document as a separate entry
        result = collection.insert_many(data_list)
        
        # Success!
        return True, f"Data for {len(result.inserted_ids)} Rukkas saved successfully."
        
    except Exception as e:
        # Handle common, specific errors
        print(f"MongoDB Error: {e}")
        if "Authentication failed" in str(e):
            return False, "Failed to save data: Authentication failed. Please check your username and password."
        elif "could not be reached" in str(e):
             return False, "Failed to save data: Cannot connect to MongoDB. Check cluster URL and network access."
        return False, f"Failed to save data: {e}"

# --- Callbacks for State Management ---
# Callbacks are functions that run when a widget is interacted with (e.g., on_change)

def reset_process():
    """
    Clears all session state variables to reset the app.
    This is called by the "Reset Process" button.
    """
    # List of all custom keys we've added to session_state
    keys_to_clear = [
        "extraction_done", 
        "result_list", 
        "current_edit_index",
        "active_input", 
        "camera_open",
        "individual_json_editor" # Also clear the editor state
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            st.session_state[key] = None
    
    st.session_state.result_list = []
    st.session_state.extraction_done = False
    
    # This is the "key-switching" trick to reset the upload/camera widgets
    st.session_state.reset_counter += 1
    st.session_state.camera_open = False # Ensure camera is reset
    
    # Force a full rerun of the script to apply all resets
    st.rerun()

def set_active_input_upload():
    """Callback for the file_uploader's on_change event."""
    st.session_state.active_input = "upload"
    # Clear old data when a new image is uploaded
    st.session_state.extraction_done = False
    st.session_state.result_list = []
    st.session_state.current_edit_index = 0

def set_active_input_camera():
    """Callback for the camera_input's on_change event."""
    st.session_state.active_input = "camera"
    # Clear old data when a new photo is snapped
    st.session_state.extraction_done = False
    st.session_state.result_list = []
    st.session_state.current_edit_index = 0
    st.session_state.camera_open = False # Close camera after snapping

# --- PAGINATION CALLBACKS (WITH BUG FIX) ---
def save_and_go_next():
    """
    Saves the content of the individual editor to the main list
    and then increments the index to show the next item.
    """
    try:
        # Get the edited text from the text box
        edited_str = st.session_state.individual_json_editor
        # Validate it's still good JSON
        new_dict = json.loads(edited_str)
        
        # Save the valid edit back into our master list
        st.session_state.result_list[st.session_state.current_edit_index] = new_dict
        
        # Move the index to the next item
        st.session_state.current_edit_index += 1
        
        # --- *** THIS IS THE FIX *** ---
        # NOW, manually update the text box's state for the *next* item
        next_item_json = json.dumps(st.session_state.result_list[st.session_state.current_edit_index], indent=2)
        st.session_state.individual_json_editor = next_item_json
        # --- *** END OF FIX *** ---
        
    except json.JSONDecodeError:
        st.error("Invalid JSON! Please fix the errors (e.g., missing comma, quote) before moving to the next item.")
    except Exception as e:
        st.error(f"An error occurred: {e}")

def save_and_go_prev():
    """
    Saves the content of the individual editor to the main list
    and then decrements the index to show the previous item.
    """
    try:
        # Get the edited text from the text box
        edited_str = st.session_state.individual_json_editor
        # Validate it's still good JSON
        new_dict = json.loads(edited_str)
        
        # Save the valid edit back into our master list
        st.session_state.result_list[st.session_state.current_edit_index] = new_dict
        
        # Move the index to the previous item
        st.session_state.current_edit_index -= 1
        
        # --- *** THIS IS THE FIX *** ---
        # NOW, manually update the text box's state for the *previous* item
        prev_item_json = json.dumps(st.session_state.result_list[st.session_state.current_edit_index], indent=2)
        st.session_state.individual_json_editor = prev_item_json
        # --- *** END OF FIX *** ---
        
    except json.JSONDecodeError:
        st.error("Invalid JSON! Please fix the errors (e.g., missing comma, quote) before moving to the next item.")
    except Exception as e:
        st.error(f"An error occurred: {e}")

# --- Main App UI ---
# This is the main part of the script that Streamlit runs.

# --- 1. Sidebar ---
# The sidebar holds controls and secondary information.
with st.sidebar:
    st.title("📄 Controls")
    
    # The "How to Use" section is in an expander to save space
    with st.expander("🤔 How to Use This Rukka App", expanded=True): # Expanded by default
        st.info("This app uses AI to read your Rukka (Purchase Slip) and turn it into structured JSON data.")
        st.write("""
            1.  **Provide Rukka Image(s):** Use either the "Upload a File" or "Take a Picture" tab. You can upload multiple files at once, **including multi-page PDFs!**
            2.  **Extract Data:** Click the 'Extract Data' button and wait for the AI to process all files.
            3.  **Review & Edit:** The AI's extracted Rukka data will appear **one by one**. Use the 'Next' and 'Previous' buttons to edit each slip individually.
            4.  **Download:** Download your *entire edited batch* as a `.json`, `.txt`, `.csv` (multi-row), or `.pdf` (multi-page) file.
            5.  **Save to DB:** Click 'Save All to MongoDB' to send all the extracted Rukkas (with your edits) to your database as separate entries.
            6.  **Reset:** Click "Reset Process" to start over.
        """)
        st.write("---")
        st.write("To change themes, click the `...` in the top-right, go to `Settings`, and choose `Light` or `Dark`.")

# --- 2. Main Page Title & Reset Button ---
# --- *** THIS IS THE FIX *** ---
# We create two columns, one for the title and one for the button
title_col, button_col = st.columns([4, 1]) # Give title 4x space of button

with title_col:
    st.title("🤖 Raw Jute Rukka Processor")
    st.write("Upload one or more images (JPG, PNG) or PDFs of a Rukka (Purchase Slip), and let AI extract the data for you.")

with button_col:
    st.write("") # Pushes button down vertically
    if st.button("🔄 Reset Process", use_container_width=True, help="Click to clear all data and start over"):
        reset_process()
# --- *** END OF FIX *** ---


if MY_API_KEY == "YOUR_API_KEY_GOES_HERE" or MY_API_KEY == "":
    st.error("🚨 CRITICAL ERROR: API Key not set! 🚨")
    st.warning("""
        **For Local Testing:**
        1. Create a folder named `.streamlit` in your project directory.
        2. Inside that folder, create a file named `secrets.toml`.
        3. Add this line to the file: `MY_API_KEY = "YOUR_KEY_HERE"`
        
        **For Deployment:**
        Go to your Streamlit Community Cloud settings and add `MY_API_KEY` to your app's secrets.
    """)
    st.stop()
else:
    # --- 3. Step 1: Provide an Image (with Tabs) ---
    # We use a container with a border to create a "card" effect.
    with st.container(border=True):
        st.header("Step 1: Provide Rukka Image(s)")
        
        tab1, tab2 = st.tabs(["📁 Upload File(s)", "📸 Take a Picture"])

        # Generate dynamic keys based on the reset counter.
        # This is the other half of the "key-switching" trick for resetting.
        upload_key = f"uploaded_file_key_{st.session_state.reset_counter}"
        camera_key = f"camera_file_key_{st.session_state.reset_counter}"
        
        with tab1:
            # --- BATCH PROCESSING UPDATE ---
            # The file uploader widget now accepts multiple files AND PDFs
            uploaded_files = st.file_uploader(
                "Choose one or more Rukka scans (PNG, JPG, JPEG, PDF)...", 
                type=["jpg", "jpeg", "png", "pdf"], # --- NEW: ADDED PDF ---
                key=upload_key,
                on_change=set_active_input_upload, # Call back to set state
                accept_multiple_files=True 
            )
        
        with tab2:
            # This logic creates the "Open/Close Camera" button flow
            if not st.session_state.camera_open:
                # State 1: Show the "Open" button
                if st.button("Open Camera", use_container_width=True):
                    st.session_state.camera_open = True
                    st.rerun() # Force rerun to show the camera widget
            else:
                # State 2: Show the camera widget and the "Close" button
                camera_file = st.camera_input(
                    "Snap a picture of your Rukka",
                    key=camera_key,
                    on_change=set_active_input_camera # Call back to set state
                )
                if st.button("Close Camera", use_container_width=True):
                    st.session_state.camera_open = False
                    st.rerun() # Force rerun to hide the camera widget

        
        image_data_list = [] # This holds the raw file uploads
        images_to_process = [] # This will hold the PIL.Image objects
        file_names_to_process = [] # This will hold their names
        
        if st.session_state.active_input == "upload":
            image_data_list = st.session_state.get(upload_key, [])
        elif st.session_state.active_input == "camera":
            camera_file_data = st.session_state.get(camera_key)
            if camera_file_data:
                image_data_list = [camera_file_data] # Put the single file in a list
        
        # --- *** THIS IS THE FIX: 50 FILE LIMIT *** ---
        if len(image_data_list) > 50:
            st.error(f"Batch Limit Exceeded: You uploaded {len(image_data_list)} files. Please select a maximum of 50 files at a time.")
            # We clear the state to stop processing
            st.session_state.active_input = None
            image_data_list = []
        # --- *** END OF FIX *** ---


        # This block only runs if an image has been provided
        if image_data_list:
            
            # Create two columns: one for the image, one for the button
            col1, col2 = st.columns([2, 3]) 
            
            with col1:
                # Show the single camera image, or a count of uploaded files
                if st.session_state.active_input == "camera":
                    img = Image.open(image_data_list[0])
                    st.image(img, caption="Your Rukka Image", width=300)
                else:
                    st.info(f"📁 {len(image_data_list)} file(s) selected.")
                    # Show a preview of the first few filenames
                    for f in image_data_list[:3]:
                        st.caption(f" - {f.name}")
                    if len(image_data_list) > 3:
                        st.caption(f"   ...and {len(image_data_list) - 3} more.")

            
            with col2:
                # Add a specific confirmation message
                if st.session_state.active_input == "camera":
                    st.success("✅ Photo captured and ready!")
                else:
                    st.info(f"{len(image_data_list)} file(s) provided. Ready to extract?")
                
                # The main "Extract" button
                if st.button(f"✨ Extract Data from {len(image_data_list)} file(s)", type="primary", use_container_width=True):
                    
                    # This is the main processing loop
                    all_results = []
                    
                    with st.spinner("🤖 Detective Gemini is processing... This may take a moment."):
                        
                        # --- NEW: PDF PRE-PROCESSING STEP ---
                        st.session_state.extraction_done = False
                        st.session_state.result_list = []
                        st.session_state.current_edit_index = 0
                        
                        images_to_process = [] # This will hold image bytes
                        image_names = [] # This will hold their names for the progress bar

                        preprocess_bar = st.progress(0, text="Pre-processing files (converting PDFs)...")
                        
                        for i, uploaded_file in enumerate(image_data_list):
                            file_name = f"File {i+1}"
                            if hasattr(uploaded_file, 'name'):
                                file_name = uploaded_file.name

                            preprocess_bar.progress((i + 1) / len(image_data_list), text=f"Loading {file_name}...")
                            
                            if uploaded_file.type == "application/pdf":
                                try:
                                    # Open the PDF from in-memory bytes
                                    doc = fitz.open(stream=uploaded_file.getvalue(), filetype="pdf")
                                    # Iterate through each page
                                    for page_num, page in enumerate(doc):
                                        # Render page to a high-DPI image (200 DPI for good OCR)
                                        pix = page.get_pixmap(dpi=200)
                                        # --- *** THIS IS THE FIX *** ---
                                        # 3. Append the raw image BYTES
                                        img_bytes = pix.tobytes("png") 
                                        images_to_process.append(img_bytes) 
                                        image_names.append(f"{file_name} (Page {page_num + 1})")
                                    doc.close()
                                except Exception as e:
                                    st.warning(f"Could not read PDF {file_name}. Skipping. Error: {e}")
                            
                            else: # It's a JPG, PNG, etc.
                                # --- *** THIS IS THE FIX *** ---
                                # 4. Get the raw BYTES from the uploader
                                uploaded_file.seek(0) # Rewind the file buffer
                                img_bytes = uploaded_file.getvalue() 
                                images_to_process.append(img_bytes) # Append the bytes
                                image_names.append(file_name)
                        
                        preprocess_bar.empty() # Remove pre-processing bar
                        # --- END OF PDF PRE-PROCESSING ---


                        # --- MAIN BATCH PROCESSING LOOP (NOW ON BYTES) ---
                        total_images_to_process = len(images_to_process)
                        if total_images_to_process > 0:
                            progress_text = f"Starting AI extraction for {total_images_to_process} image(s)..."
                            my_bar = st.progress(0, text=progress_text)
                            
                            # 5. Loop over the image BYTES
                            for i, img_bytes in enumerate(images_to_process):
                                file_name = image_names[i]

                                # Update progress bar
                                progress_text = f"Processing {i+1}/{total_images_to_process}: {file_name}"
                                my_bar.progress((i + 1) / total_images_to_process, text=progress_text)
                                
                                # 6. Pass the image BYTES to the cached function
                                json_string = get_json_from_image(img_bytes, MY_API_KEY)
                                
                                if json_string:
                                    # Success, parse the JSON and add to our list
                                    try:
                                        all_results.append(json.loads(json_string))
                                    except Exception as e:
                                        st.warning(f"File {file_name} processing failed. AI returned invalid JSON. Error: {e}")
                                else:
                                    # Failure
                                    st.warning(f"File {file_name} processing failed. AI returned no data.")
                            
                            # --- End of loop ---
                            my_bar.empty() # Remove progress bar
                        
                        if all_results:
                            # --- PAGINATION UPDATE ---
                            st.session_state.result_list = all_results
                            st.session_state.current_edit_index = 0
                            st.session_state.extraction_done = True
                            
                            # --- *** THIS IS THE FIX *** ---
                            # Pre-load the editor state with the *first* item.
                            first_item_json = json.dumps(st.session_state.result_list[0], indent=2)
                            st.session_state.individual_json_editor = first_item_json
                            # --- *** END OF FIX *** ---
                            
                            st.success(f"Extraction Complete! {len(all_results)}/{total_images_to_process} Rukkas processed. See results in Step 2.")
                        else:
                            st.error("Extraction failed. No files could be processed.")

    st.divider()

    # --- 4. Step 2 & 3: Review, Edit, & Download ---
    # This entire section only appears *after* data has been extracted.
    if st.session_state.extraction_done and st.session_state.result_list:
        
        with st.container(border=True):
            st.header("Step 2: Review & Edit Rukka Data")
            
            # --- PAGINATION UI ---
            total_items = len(st.session_state.result_list)
            current_index = st.session_state.current_edit_index
            
            # Get the JSON for the current item
            # --- *** THIS IS THE FIX *** ---
            # We no longer read from the list here, we just set the title.
            # The text_area is now fully controlled by its own state.
            st.write(f"You are editing **Rukka {current_index + 1} of {total_items}**. (Edits are saved when you click 'Next' or 'Previous'.)")
            
            # The individual JSON text editor
            edited_json_text = st.text_area(
                "Editable Rukka JSON", 
                key="individual_json_editor", # The key holds the state
                height=400
                # We remove the `value=...` argument.
                # The state `individual_json_editor` is now the single source of truth.
            )
            # --- *** END OF FIX *** ---

            # --- PAGINATION BUTTONS ---
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col1:
                st.button(
                    "⬅️ Previous", 
                    on_click=save_and_go_prev, 
                    use_container_width=True,
                    disabled=(current_index == 0) # Disable on first item
                )
            
            with col2:
                # This is just a spacer
                pass
            
            with col3:
                st.button(
                    "Next ➡️", 
                    on_click=save_and_go_next, 
                    use_container_width=True,
                    disabled=(current_index >= total_items - 1) # Disable on last item
                )

            # --- END OF PAGINATION UI ---


            st.header("Step 3: Download & Export All Rukka Data")
            try:
                try:
                    last_edit_str = st.session_state.individual_json_editor
                    last_edit_dict = json.loads(last_edit_str)
                    st.session_state.result_list[current_index] = last_edit_dict
                except Exception as e:
                    st.error(f"Could not save last edit: {e}")
                # --- *** END OF FIX *** ---
                
                full_edited_json_text = json.dumps(st.session_state.result_list, indent=2)
                is_valid_json = True
            except Exception as e:
                st.error(f"Could not prepare data for download. Error: {e}")
                full_edited_json_text = "[]"
                is_valid_json = False


            if is_valid_json:
                # --- Download as a File ---
                st.subheader("Download Full Batch Report")
                col1, col2, col3, col4 = st.columns(4)
                
                # A. Download as JSON
                col1.download_button(
                    label="⬇️ Download as .json",
                    data=full_edited_json_text, # Use the new full string
                    file_name="rukka_data_batch.json",
                    mime="application/json",
                    use_container_width=True
                )
                
                # B. Download as TXT
                with col2:
                    try:
                        text_report_data = create_text_report(full_edited_json_text)
                        st.download_button(
                            label="⬇️ Download as .txt",
                            data=text_report_data,
                            file_name="rukka_data_batch.txt",
                            mime="text/plain",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error("Could not create TXT.")
                        print(f"TXT Creation Error: {e}")
                
                # C. Download as CSV
                with col3:
                    try:
                        data_dict = json.loads(full_edited_json_text)
                        df = pd.json_normalize(data_dict)
                        csv_string = df.to_csv(index=False).encode('utf-8')
                        
                        st.download_button(
                            label="⬇️ Download as .csv",
                            data=csv_string,
                            file_name="rukka_data_batch.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error("Could not convert to CSV.")
                        st.info("CSV conversion works best for flat JSON or data with a single list of items.")
                        print(f"CSV Conversion Error: {e}")

                # D. Download as PDF
                with col4:
                    try:
                        pdf_data = create_pdf(full_edited_json_text)
                        st.download_button(
                            label="⬇️ Download as .pdf",
                            data=pdf_data,
                            file_name="rukka_data_batch.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error("Could not create PDF.")
                        print(f"PDF Creation Error: {e}")
                
                st.divider()

                # --- Save to Database ---
                st.subheader("Save All Rukkas to Database")
                
                if st.button("💾 Save All to MongoDB", use_container_width=True, type="primary"):
                    # Edge Case: Check for Mongo credentials
                    if MONGO_USER == "YOUR_MONGO_USERNAME" or MONGO_PASSWORD == "YOUR_MONGO_PASSWORD" or MONGO_CLUSTER_URL == "YOUR_MONGO_CLUSTER_URL_HERE" or MONGO_USER == "":
                        st.error("🚨 ERROR: MongoDB Connection details not set! 🚨")
                        st.warning("""
                            **For Local Testing:**
                            1. Open your `.streamlit/secrets.toml` file.
                            2. Add these lines:
                               `MONGO_USER = "YOUR_MONGO_USERNAME"`
                               `MONGO_PASSWORD = "YOUR_MONGO_PASSWORD"`
                               `MONGO_CLUSTER_URL = "YOUR_MONGO_CLUSTER_URL_HERE"`
                            
                            **For Deployment:**
                            Go to your Streamlit Community Cloud settings and add these three secrets.
                        """)
                    else:
                        # Show spinner while saving
                        with st.spinner("Connecting to database and saving batch..."):
                            success, message = save_to_mongodb(
                                MONGO_USER, 
                                MONGO_PASSWORD, 
                                MONGO_CLUSTER_URL, 
                                full_edited_json_text # Send the full edited string
                            )
                            if success:
                                st.success(message)
                            else:
                                st.error(message)

            else:
                # If the text box is empty
                st.info("The JSON text box is empty. Extract or edit data to enable downloads.")


