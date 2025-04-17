import streamlit as st
import boto3
import openai
import os

# === Constants and Configuration ===
AWS_ACCESS_KEY = st.secrets["AWS_ACCESS_KEY"]
AWS_SECRET_KEY = st.secrets["AWS_SECRET_KEY"]
REGION = st.secrets["REGION"]
S3_BUCKET = st.secrets["S3_BUCKET"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
LOCAL_SAVE_DIR = "downloads"

# === Initialize Clients ===
s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=REGION
)

openai.api_key = OPENAI_API_KEY

# === S3 Utility Functions ===
def list_all_s3_files():
    paginator = s3_client.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=S3_BUCKET)

    all_files = []
    for page in page_iterator:
        for obj in page.get('Contents', []):
            key = obj['Key']
            if not key.endswith('/'):
                all_files.append(key)
    return all_files

def ask_gpt_for_matching_files(user_query, file_keys):
    system_prompt = (
        "You are an assistant that maps user queries to full S3 file paths. "
        "Return only full file paths from the list that match the query. "
        "If nothing matches, reply 'No matching files found.'"
    )

    user_prompt = f"Query: {user_query}\nAvailable file paths:\n" + "\n".join(file_keys)

    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.5,
    )

    reply = response['choices'][0]['message']['content']
    
    if 'No matching files' in reply:
        return []

    matched_files = []
    reply_lines = [line.strip() for line in reply.splitlines()]
    file_key_map = {os.path.basename(key).lower(): key for key in file_keys}

    for line in reply_lines:
        filename = os.path.basename(line.strip()).lower()
        if filename in file_key_map:
            matched_files.append(file_key_map[filename])
    
    return matched_files

def download_files_from_s3(full_s3_keys):
    os.makedirs(LOCAL_SAVE_DIR, exist_ok=True)
    downloaded_files = []

    for s3_key in full_s3_keys:
        file_name = os.path.basename(s3_key)
        try:
            response = s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
            file_data = response['Body'].read()
            file_path = os.path.join(LOCAL_SAVE_DIR, file_name)

            with open(file_path, 'wb') as f:
                f.write(file_data)

            downloaded_files.append(file_path)
        except Exception as e:
            st.error(f"❌ Failed to download {s3_key}: {e}")
    
    return downloaded_files

# === Streamlit UI ===
st.title("📁 S3 File Finder & Downloader with GPT")
st.markdown("Type a natural-language query to find matching files in your S3 bucket.")

if "matched_files" not in st.session_state:
    st.session_state.matched_files = []

# Input for query
user_query = st.text_input("🔍 Enter your file search query:")

if st.button("Run") and user_query:
    with st.spinner("Listing files from S3..."):
        files = list_all_s3_files()

    if not files:
        st.warning("No files found in the S3 bucket.")
    else:
        with st.spinner("Asking GPT to find matching files..."):
            matched_files = ask_gpt_for_matching_files(user_query, files)
            st.session_state.matched_files = matched_files

# Show multiselect if we have results
if st.session_state.matched_files:
    st.success("✅ GPT matched the following files:")

    for f in st.session_state.matched_files:
        st.code(f)

    selection = st.multiselect(
        "📂 Select files to download (or leave empty to download all):",
        st.session_state.matched_files
    )

    files_to_download = selection if selection else st.session_state.matched_files

    if st.button("📥 Download Selected"):
        with st.spinner("Downloading..."):
            downloaded_paths = download_files_from_s3(files_to_download)

        for file_path in downloaded_paths:
            with open(file_path, "rb") as file:
                st.download_button(
                    label=f"⬇️ Download {os.path.basename(file_path)}",
                    data=file,
                    file_name=os.path.basename(file_path),
                    key=file_path
                )
elif user_query:
    st.error("🚫 No matching files found.")
