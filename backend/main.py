import os
import requests
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from pyairtable import Api
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables, overriding any existing system ones to ensure fresh reads
load_dotenv(override=True)

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
VAPI_PUBLIC_KEY = os.getenv("VAPI_PUBLIC_KEY")
VAPI_ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID")

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REFRESH_TOKEN = os.getenv("ZOHO_REFRESH_TOKEN")

def get_zoho_access_token():
    url = "https://accounts.zoho.com/oauth/v2/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": ZOHO_CLIENT_ID,
        "client_secret": ZOHO_CLIENT_SECRET,
        "refresh_token": ZOHO_REFRESH_TOKEN
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        data = response.json()
        if "access_token" in data:
            return data["access_token"]
        else:
            raise HTTPException(status_code=500, detail=f"Zoho token refresh succeeded (200 OK) but returned an error payload: {data}")
    else:
        raise HTTPException(status_code=500, detail=f"Failed to refresh Zoho token: {response.text}")

app = FastAPI(title="Vapi B2B Token Vendor")

# Configure CORS so the frontend can successfully make requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to specific domains in production for better security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/generate-token")
def generate_token(company: str = Query(..., description="The company name to look up")):
    """
    Endpoint to look up a company in Airtable and generate a secure WebRTC token from Vapi.
    """
    if "zohodemo" in company.lower():
        try:
            access_token = get_zoho_access_token()
            headers = {
                "Authorization": f"Zoho-oauthtoken {access_token}"
            }
            # Search candidate by email
            search_url = "https://recruit.zoho.com/recruit/v2/Candidates/search?criteria=(Email:equals:[DUMMY_EMAIL])"
            response = requests.get(search_url, headers=headers)
            
            if response.status_code == 204:
                raise HTTPException(status_code=404, detail="Candidate not found in Zoho (204 No Content).")
            elif response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=f"Zoho API error: {response.text}")
                
            data = response.json()
            if not data.get("data"):
                raise HTTPException(status_code=404, detail="Candidate not found in Zoho.")
                
            candidate = data["data"][0]
            first_name = candidate.get("First_Name", "Guest")
            status = candidate.get("Candidate_Status", "New")
            
            return {
                "companyName": company,
                "jobTitle": "Candidate",
                "firstName": first_name,
                "vapi_public_key": VAPI_PUBLIC_KEY,
                "assistant_id": VAPI_ASSISTANT_ID,
                "assistantOverrides": {
                    "variableValues": {
                        "firstName": first_name,
                        "status": status
                    }
                }
            }
        except HTTPException as he:
            raise he
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, VAPI_PUBLIC_KEY, VAPI_ASSISTANT_ID]):
        raise HTTPException(status_code=500, detail="Missing server configuration.")

    try:
        # 1. Query Airtable
        api = Api(AIRTABLE_API_KEY)
        table = api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)
        
        # Searching by Output field (which contains the full hostname)
        # Note: Using formula matching exact string. Escape single quotes if necessary.
        safe_company = company.replace("'", "\\'")
        formula = f"{{Output}} = '{safe_company}'"
        records = table.all(formula=formula)

        if not records:
            raise HTTPException(status_code=404, detail="Company not found in Airtable.")

        # Extract the first matching record
        record_fields = records[0].get("fields", {})
        fetched_company_name = record_fields.get("companyName", company)
        job_title = record_fields.get("jobTitle", "Professional")
        
        # Extract first name
        full_name = record_fields.get("Name", "Guest")
        first_name = full_name.split()[0] if full_name and full_name.strip() else "Guest"

        # We no longer need to call Vapi from the backend since we are dynamically sending
        # the Public Key to the frontend. This keeps the frontend source code "dumb"
        # and free of hardcoded API keys while ensuring we don't get 401 Unauthorized errors.
        
        return {
            "companyName": fetched_company_name,
            "jobTitle": job_title,
            "firstName": first_name,
            "vapi_public_key": VAPI_PUBLIC_KEY,
            "assistant_id": VAPI_ASSISTANT_ID
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ZohoUpdateRequest(BaseModel):
    candidate_id: str
    new_status: str

@app.post("/api/update-zoho")
def update_zoho(payload: dict = Body(...)):
    # Try flat structure
    candidate_id = payload.get("candidate_id")
    new_status = payload.get("new_status")
    tool_call_id = None
    
    # Try Vapi Custom Tool structure
    if not candidate_id and "message" in payload:
        try:
            tool_calls = payload["message"].get("toolCalls", [])
            if tool_calls:
                tool_call_id = tool_calls[0].get("id")
                arguments = tool_calls[0]["function"]["arguments"]
                if isinstance(arguments, str):
                    import json
                    arguments = json.loads(arguments)
                candidate_id = arguments.get("candidate_id")
                new_status = arguments.get("new_status")
        except Exception:
            pass

    if not candidate_id or not new_status:
        raise HTTPException(status_code=400, detail="Missing candidate_id or new_status in payload")

    try:
        access_token = get_zoho_access_token()
        headers = {
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "Content-Type": "application/json"
        }
        update_url = f"https://recruit.zoho.com/recruit/v2/Candidates/{candidate_id}"
        update_payload = {
            "data": [
                {
                    "Candidate_Status": new_status
                }
            ]
        }
        response = requests.put(update_url, headers=headers, json=update_payload)
        
        if response.status_code in [200, 201, 202, 204]:
            if tool_call_id:
                # Return Vapi specific Custom Tool response format if it was a Vapi call
                return {
                    "results": [
                        {
                            "toolCallId": tool_call_id,
                            "result": "Success"
                        }
                    ]
                }
            # Otherwise return standard 200 OK
            return {"message": "Success"}
        else:
            raise HTTPException(status_code=response.status_code, detail=f"Zoho update failed: {response.text}")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
