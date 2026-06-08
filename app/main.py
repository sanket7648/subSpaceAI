from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from . import models, schemas, database
from .database import engine
from .services.ocean_service import get_lookalike_companies
from .services.prospeo_service import enrich_leads_bulk, search_decision_makers
from .services.brevo_service import send_outreach_email
import asyncio
import os

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Outreach Pipeline API")

@app.get("/test-prospeo/")
async def test_prospeo(domain: str = "hubspot.com"):
    """Debug endpoint to test Prospeo API with different parameter names"""
    api_key = os.getenv("PROSPEO_API_KEY")
    if not api_key:
        return {"error": "PROSPEO_API_KEY not set in environment"}
        
    import httpx
    import asyncio
        
    url = "https://api.prospeo.io/search-person"
    headers = {"X-KEY": api_key, "Content-Type": "application/json"}
        
    test_payloads = [
        {"filters": {"company_website": {"include": [domain]}, "person_job_title": {"include": ["CEO"]}}},
        {"filters": {"company_domain": {"include": [domain]}, "person_job_title": {"include": ["CEO"]}}},
        {"company_website": domain, "job_title": "CEO"} 
    ]
        
    results = []
    async with httpx.AsyncClient() as client:
        for i, payload in enumerate(test_payloads):
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                response_data = response.json() if response.status_code == 200 else {"raw": response.text[:200]}
                                
                results.append({
                    "test": i + 1,
                    "payload": payload,
                    "status": response.status_code,
                    "response": response_data
                })
                print(f"Test {i+1}: {response.status_code} - {payload}")
                
                await asyncio.sleep(1.5)
                
            except Exception as e:
                results.append({"test": i + 1, "payload": payload, "error": str(e)})
                
    return {"test_results": results}

@app.post("/run-pipeline/")
async def trigger_pipeline(seed_domain: str, db: Session = Depends(database.get_db)):
    new_run = models.PipelineRun(seed_domain=seed_domain, status="running")
    db.add(new_run)
    db.commit()
    db.refresh(new_run)

    try:
        # --- STAGE 1: OCEAN.IO ---
        print(f"Starting Stage 1: Finding lookalikes for {seed_domain}")
        lookalike_domains = await get_lookalike_companies(seed_domain=seed_domain)
        
        if not lookalike_domains:
            raise ValueError(f"No lookalike companies found for {seed_domain}")
            
        for domain in lookalike_domains:
            new_company = models.Company(run_id=new_run.id, domain=domain)
            db.add(new_company)
        db.commit()
        
        new_run.status = "completed_stage_1"
        db.commit()

        # --- STAGE 2: PROSPEO ---
        print("Starting Stage 2: Finding and enriching decision-makers (including emails)")
        
        companies = db.query(models.Company).filter(models.Company.run_id == new_run.id).all()
        all_leads = []
        resolved_emails_count = 0
        final_summary = []

        for company in companies:
            leads_data = await search_decision_makers(company.domain)
            
            if leads_data:
                enrich_payload = []
                for i, lead in enumerate(leads_data):
                    person_id = lead.get("id") or lead.get("person_id")
                    linkedin = lead.get("linkedin_url") or lead.get("linkedin")
                    
                    payload_item = {"identifier": str(i)}
                    
                    if person_id:
                        payload_item["person_id"] = person_id
                    elif linkedin:
                        payload_item["linkedin_url"] = linkedin
                    else:
                        payload_item.update({
                            "full_name": lead.get("full_name") or lead.get("name"),
                            "company_website": company.domain
                        })
                    
                    enrich_payload.append(payload_item)
                
                if enrich_payload:
                    bulk_results = await enrich_leads_bulk(enrich_payload)
                    
                    for match in bulk_results.get("matched", []):
                        person = match.get("person", {})
                        if isinstance(person, dict):
                            email_data = person.get("email")
                            work_email = None
                            if isinstance(email_data, dict):
                                work_email = email_data.get("email")
                            elif isinstance(email_data, str):
                                work_email = email_data
                                
                            new_lead = models.Lead(
                                company_id=company.id,
                                name=person.get("full_name"),
                                linkedin_url=person.get("linkedin_url"),
                                work_email=work_email
                            )
                            db.add(new_lead)
                            all_leads.append(new_lead)
                            
                            if work_email:
                                resolved_emails_count += 1
                                final_summary.append({
                                    "name": new_lead.name,
                                    "company": company.domain,
                                    "email": work_email
                                })
            
            db.commit()

        if not all_leads:
            raise ValueError("No decision makers found across any lookalike domains.")

        new_run.status = "pending_checkpoint"
        db.commit()

        return {
            "message": "Pipeline paused at safety checkpoint. Review leads before sending emails.", 
            "run_id": new_run.id,
            "metrics": {
                "domains_found": len(companies),
                "leads_found": len(all_leads),
                "emails_resolved": resolved_emails_count
            },
            "ready_to_email": final_summary
        }
        
    except Exception as e:
        new_run.status = f"failed: {str(e)}"
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

# CRITICAL FIX: This endpoint is now completely outside the previous function
@app.post("/approve-and-send/{run_id}")
async def approve_and_send_emails(run_id: int, db: Session = Depends(database.get_db)):
    """
    Safety Checkpoint Approval: Sends emails to all resolved leads in a specific run.
    """
    run = db.query(models.PipelineRun).filter(models.PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
        
    if run.status != "pending_checkpoint":
        raise HTTPException(status_code=400, detail=f"Run is not waiting at the checkpoint. Current status: {run.status}")

    companies = db.query(models.Company).filter(models.Company.run_id == run_id).all()
    company_ids = [c.id for c in companies]
    
    leads = db.query(models.Lead).filter(
        models.Lead.company_id.in_(company_ids),
        models.Lead.work_email != None
    ).all()
    
    if not leads:
        return {"message": "No valid emails found to send for this run."}
        
    print(f"Starting email sequence for {len(leads)} leads...")
    
    success_count = 0
    for lead in leads:
        company_domain = lead.company.domain
        first_name = lead.name.split(" ")[0] if lead.name else "there"
        
        print(f"Sending email to {lead.work_email}...")
        
        success = await send_outreach_email(
            to_email=lead.work_email,
            to_name=first_name,
            company_name=company_domain
        )
        
        if success:
            success_count += 1
            
    run.status = "completed_emails_sent"
    db.commit()
    
    return {
        "message": "Outreach sequence complete!", 
        "run_id": run_id,
        "metrics": {
            "attempted": len(leads),
            "successfully_sent": success_count
        }
    }