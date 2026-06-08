import os
import httpx
from fastapi import HTTPException
from typing import List

OCEAN_API_KEY = os.getenv("OCEAN_API_KEY")
OCEAN_API_URL = "https://api.ocean.io/v3/search/companies" 

async def get_lookalike_companies(seed_domain: str, limit: int = 5) -> List[str]:
    if not OCEAN_API_KEY:
        raise ValueError("OCEAN_API_KEY is missing from environment variables.")

    headers = {
        "X-Api-Token": OCEAN_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "size": limit,
        "companiesFilters": {
            "lookalikeDomains": [seed_domain]
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(OCEAN_API_URL, json=payload, headers=headers, timeout=15.0)
            response.raise_for_status() 
            
            data = response.json()
            
            results = data.get("companies", [])
            
            lookalikes = [
                item.get("company", {}).get("domain") 
                for item in results 
                if isinstance(item, dict) and item.get("company", {}).get("domain")
            ]
            
            if not lookalikes:
                raise ValueError(f"No domains extracted. Verify seed domain has lookalikes.")
                
            return lookalikes
        
        except httpx.HTTPStatusError as e:
            error_detail = f"Ocean.io API Error: Status {e.response.status_code}"
            raise HTTPException(status_code=e.response.status_code, detail=error_detail)
            
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail="Failed to connect to Ocean.io")