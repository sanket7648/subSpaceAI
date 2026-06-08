from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, index=True)
    seed_domain = Column(String, index=True)
    status = Column(String, default="started") # started, completed, failed
    
    companies = relationship("Company", back_populates="run")

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("pipeline_runs.id"))
    domain = Column(String)
    
    run = relationship("PipelineRun", back_populates="companies")
    leads = relationship("Lead", back_populates="company")

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    work_email = Column(String, nullable=True)
    email_sent = Column(Boolean, default=False)

    company = relationship("Company", back_populates="leads")