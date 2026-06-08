import asyncio
import os

from app.database import SessionLocal, engine
from app import models

from app.services.ocean_service import get_lookalike_companies
from app.services.prospeo_service import enrich_leads_bulk, search_decision_makers
from app.services.brevo_service import send_outreach_email

# Ensure database tables are created
models.Base.metadata.create_all(bind=engine)

async def run_pipeline():
    print("\n==================================================")
    print("      AI Outreach Pipeline - CLI          ")
    print("==================================================\n")
    
    # User only needs to enter the domain
    seed_domain = input("Enter the seed domain (e.g., hubspot.com): ").strip()
    
    if not seed_domain:
        print("Domain cannot be empty. Exiting.")
        return

    db = SessionLocal()
    new_run = models.PipelineRun(seed_domain=seed_domain, status="running")
    db.add(new_run)
    db.commit()
    db.refresh(new_run)

    try:
        # --- STAGE 1: OCEAN.IO ---
        print(f"\n[Stage 1] Finding lookalike companies for {seed_domain}...")
        lookalike_domains = await get_lookalike_companies(seed_domain=seed_domain)
        
        if not lookalike_domains:
            print("No lookalikes found. Pipeline stopped.")
            return
            
        print(f"  -> Found {len(lookalike_domains)} domains: {', '.join(lookalike_domains)}")
        
        for domain in lookalike_domains:
            new_company = models.Company(run_id=new_run.id, domain=domain)
            db.add(new_company)
        db.commit()

        # --- STAGE 2: PROSPEO ---
        print("\n[Stage 2] Searching & Enriching Decision Makers (Prospeo)...")
        companies = db.query(models.Company).filter(models.Company.run_id == new_run.id).all()
        all_leads = []
        valid_emails = []

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
                                valid_emails.append(new_lead)
            db.commit()

        if not all_leads:
            print("No decision makers found across the lookalike domains.")
            return
            
        print(f"  -> Successfully enriched {len(all_leads)} leads.")
        print(f"  -> {len(valid_emails)} leads have verified emails ready for outreach.\n")

        # --- SAFETY CHECKPOINT ---
        if not valid_emails:
            print("No verified emails found. Pipeline complete.")
            return

        print("==================================================")
        print("                SAFETY CHECKPOINT                 ")
        print("==================================================")
        for lead in valid_emails:
            print(f" - {lead.name} ({lead.company.domain}) -> {lead.work_email}")
        print("==================================================\n")

        choice = input("Do you want to send outreach emails to these leads? (y/n): ").strip().lower()

        if choice == 'y':
            # --- STAGE 3: BREVO OUTREACH ---
            print("\n[Stage 3] Sending Outreach Emails via Brevo...")
            success_count = 0
            
            for lead in valid_emails:
                first_name = lead.name.split(" ")[0] if lead.name else "there"
                print(f"  -> Sending to {lead.work_email}...")
                
                success = await send_outreach_email(
                    to_email=lead.work_email,
                    to_name=first_name,
                    company_name=lead.company.domain
                )
                
                if success:
                    success_count += 1
            
            new_run.status = "completed_emails_sent"
            db.commit()
            print(f"\nPipeline Complete! Successfully sent {success_count} emails.")
        else:
            new_run.status = "stopped_at_checkpoint"
            db.commit()
            print("\n Emails cancelled. Pipeline safely stopped at checkpoint.")

    except Exception as e:
        print(f"\n [Error] Pipeline failed: {str(e)}")
        new_run.status = f"failed: {str(e)}"
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    # Load environment variables if using dotenv
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
        
    asyncio.run(run_pipeline())
