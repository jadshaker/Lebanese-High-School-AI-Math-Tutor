import os
import requests
import time
from dotenv import load_dotenv
import glob
import argparse

load_dotenv()

MINERU_API_KEY = os.getenv("MINERU_API_KEY")
MINERU_URL = "https://mineru.net/api/v4/extract/task"


# --------- Parse Arguments ----------
parser = argparse.ArgumentParser(description="Upload PDFs and extract content using MinerU API")
parser.add_argument("-i", "--input", required=True, help="Input directory containing PDF files")
parser.add_argument("-o", "--output", default="latex", help="Output directory for downloaded results (default: latex)")
args = parser.parse_args()

input_dir = args.input
output_dir = args.output

# Validate input directory
if not os.path.exists(input_dir):
    raise Exception(f"Input directory does not exist: {input_dir}")
if not os.path.isdir(input_dir):
    raise Exception(f"Input path is not a directory: {input_dir}")

# Check and create output directory
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
    print(f"Created output directory: {output_dir}")
else:
    print(f"Using existing output directory: {output_dir}")

# --------- CONFIG ----------
files_to_upload = glob.glob(os.path.join(input_dir, "*.pdf"))
if not files_to_upload:
    raise Exception(f"No PDF files found in {input_dir}")

print(f"Found {len(files_to_upload)} PDF file(s) to upload")
model_version = "vlm"
poll_interval = 5  # seconds between checking batch status
# ---------------------------

# Step 1: Apply for pre-signed upload URLs
url_batch = "https://mineru.net/api/v4/file-urls/batch"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {MINERU_API_KEY}"
}

data = {
    "files": [{"name": os.path.basename(f)} for f in files_to_upload],
    "model_version": model_version
}

res = requests.post(url_batch, headers=headers, json=data)
if res.status_code != 200:
    raise Exception(f"Batch URL request failed: {res.status_code} {res.text}")

result = res.json()
if result["code"] != 0:
    raise Exception(f"Failed to get upload URLs: {result}")

batch_id = result["data"]["batch_id"]
file_urls = result["data"]["file_urls"]

# Step 2: Upload local files
for i, file_path in enumerate(files_to_upload):
    with open(file_path, "rb") as f:
        upload_res = requests.put(file_urls[i], data=f)
        if upload_res.status_code == 200:
            print(f"Uploaded {file_path} successfully")
        else:
            print(f"Failed to upload {file_path}: {upload_res.status_code} {upload_res.text}")

# Step 3: Poll for batch extraction results
url_results = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
downloaded_files = set()
while True:
    res = requests.get(url_results, headers=headers)
    if res.status_code != 200:
        print(f"Error fetching results: {res.status_code} {res.text}")
        time.sleep(poll_interval)
        continue

    result = res.json()
    if result["code"] != 0:
        print(f"API returned error: {result}")
        time.sleep(poll_interval)
        continue

    all_done = True
    for file_res in result["data"]["extract_result"]:
        state = file_res["state"]
        fname = file_res["file_name"]
        if state == "done":
            if fname not in downloaded_files:
                zip_url = file_res.get("full_zip_url")
                if zip_url:
                    # Download the zip with name based on original PDF
                    base_name = os.path.splitext(fname)[0]  # Remove .pdf extension
                    local_zip_path = os.path.join(output_dir, f"{base_name}.zip")
                    r = requests.get(zip_url)
                    if r.status_code == 200:
                        with open(local_zip_path, "wb") as f:
                            f.write(r.content)
                        print(f"Downloaded {fname} ZIP to {local_zip_path}")
                        downloaded_files.add(fname)
                    else:
                        print(f"Failed to download ZIP for {fname}: {r.status_code}")
                        all_done = False
                else:
                    print(f"No ZIP URL for {fname}")
        elif state == "running":
            progress = file_res.get("extract_progress", {})
            print(f"{fname} is running: extracted {progress.get('extracted_pages')}/{progress.get('total_pages')} pages")
            all_done = False
        elif state == "failed":
            print(f"{fname} failed: {file_res.get('err_msg')}")
            downloaded_files.add(fname)  # Mark as processed even if failed
    
    if all_done and len(downloaded_files) == len(files_to_upload):
        print(f"All files processed: {len(downloaded_files)} files")
        break

    time.sleep(poll_interval)
