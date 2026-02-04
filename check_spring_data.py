import requests
import json
import sys

# Spring API URL
BASE_URL = "http://localhost:8080/api/v1/calls"

def check_calls():
    print("Checking Spring Backend for saved calls (IDs 1-20)...")
    found_calls = 0
    
    for i in range(1, 21):
        url = f"{BASE_URL}/{i}"
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                print(f"\n[FOUND] Call ID: {data.get('id')}")
                print(f" - Phone: {data.get('phoneNumber')}")
                print(f" - Start Time: {data.get('startTime')}")
                
                # Check for analysis
                analysis_url = f"{BASE_URL}/{i}/analysis"
                analysis_resp = requests.get(analysis_url, timeout=2)
                if analysis_resp.status_code == 200 and analysis_resp.text:
                    try:
                        a_data = analysis_resp.json()
                        if a_data:
                            print(f" - Summary: {a_data.get('summaryText')}")
                            print(f" - Keywords: {a_data.get('keyword')}")
                    except:
                        print(" - Analysis: (Parsing Error or Empty)")
                else:
                    print(" - Analysis: Not found or not ready")
                
                found_calls += 1
            else:
                # print(f"Call ID {i}: Not found ({response.status_code})")
                pass
        except Exception as e:
            print(f"Error checking ID {i}: {e}")

    if found_calls == 0:
        print("\nNo calls found in range ID 1-20.")
        print("Note: If you just started the server, the ID count might be low.")
    else:
        print(f"\nTotal calls found: {found_calls}")

if __name__ == "__main__":
    check_calls()
