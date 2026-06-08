import os
import httpx
import asyncio
from typing import List, Dict

PROSPEO_API_KEY = os.getenv("PROSPEO_API_KEY")

async def search_decision_makers(domain: str) -> List[Dict]:
    """
    Step 1: Search for decision-makers.
    Extracts the nested 'person' object so main.py can read the identifiers.
    """
    url = "https://api.prospeo.io/search-person"
    headers = {"X-KEY": PROSPEO_API_KEY, "Content-Type": "application/json"}
    
    if not PROSPEO_API_KEY:
        print("PROSPEO_API_KEY not set!")
        return []
        
    payload = {
        "filters": {
            "company": {
                "websites": {
                    "include": [domain]
                }
            },
            "person_job_title": {
                "include": ["CEO", "Founder", "Director", "VP", "CTO", "CMO"]
            }
        }
    }
    
    max_retries = 3
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=20.0)
                
                if response.status_code == 200:
                    data = response.json()
                    raw_results = data.get("results", [])
                    
                    # THE FIX: Extract the nested "person" object so main.py can read person_id
                    extracted_leads = []
                    for r in raw_results:
                        person_data = r.get("person")
                        if person_data:
                            extracted_leads.append(person_data)
                            
                    print(f"  Found {len(extracted_leads)} decision makers at {domain}")
                    await asyncio.sleep(1.2)
                    return extracted_leads
                    
                elif response.status_code == 429:
                    print(f"  Rate limited at {domain}, retrying attempt {attempt+1}...")
                    await asyncio.sleep(2.5)
                    continue
                    
                elif response.status_code == 400 and "NO_RESULTS" in response.text:
                    print(f"  No leads found for {domain}")
                    await asyncio.sleep(1.2)
                    return []
                    
                else:
                    print(f"  API Error {domain}: {response.status_code} - {response.text}")
                    await asyncio.sleep(1.2)
                    return []
                    
            except Exception as e:
                print(f"  Exception at {domain}: {str(e)}")
                await asyncio.sleep(2.0)
                continue
                
    return []

async def enrich_leads_bulk(leads_to_enrich: List[Dict]) -> Dict:
    """
    Step 2: Enrich profiles one-by-one to respect the 1 req/sec limit.
    """
    if not leads_to_enrich:
        return {}

    url = "https://api.prospeo.io/enrich-person"
    headers = {"X-KEY": PROSPEO_API_KEY, "Content-Type": "application/json"}
    
    matched_results = []
    
    async with httpx.AsyncClient() as client:
        for lead in leads_to_enrich:
            # Clean up the payload for the single endpoint
            lead_data = {k: v for k, v in lead.items() if k != "identifier"}
            
            payload = {
                "only_verified_email": True,
                "data": lead_data 
            }
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = await client.post(url, json=payload, headers=headers, timeout=30.0)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if not data.get("error") and data.get("person"):
                            matched_results.append({
                                "person": data["person"],
                                "company": data.get("company", {})
                            })
                        
                        # Print the name or ID to show progress in the terminal
                        lead_name = lead_data.get("full_name") or lead_data.get("person_id") or "Lead"
                        print(f"  Enriched: {lead_name}")
                        await asyncio.sleep(1.2) # Hard break to protect 1 req/sec limits
                        break 
                        
                    elif response.status_code == 429:
                        print(f"  Enrichment rate limited, retrying attempt {attempt+1}...")
                        await asyncio.sleep(3.0)
                        continue
                        
                    else:
                        print(f"  Enrichment API Error: {response.status_code} - {response.text}")
                        await asyncio.sleep(1.2)
                        break 
                        
                except Exception as e:
                    print(f"  Exception enriching lead: {str(e)}")
                    await asyncio.sleep(2.0)
                    continue
                    
    return {"matched": matched_results}