from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime
from src.core.db import Base

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    github_url = Column(String)
    last_processed_run_id = Column(BigInteger, nullable=True) # Lưu ID lần quét cuối
    artifacts = relationship("Artifact", back_populates="project")

class Artifact(Base):
    __tablename__ = "artifacts"
    id = Column(Integer, primary_key=True, index=True)
    github_artifact_id = Column(BigInteger, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    status = Column(String, default="pending") 
    project = relationship("Project", back_populates="artifacts")
    findings = relationship("Finding", back_populates="artifact")

class Finding(Base):
    __tablename__ = "findings"
    id = Column(Integer, primary_key=True, index=True)
    artifact_id = Column(Integer, ForeignKey("artifacts.id"))
    tool = Column(String) 
    rule_id = Column(String)
    severity = Column(String)
    message = Column(String)
    file_path = Column(String)
    line_number = Column(Integer)
    fingerprint = Column(String, index=True, nullable=True) 
    raw_data = Column(JSON) 
    cwe_id = Column(String, nullable=True)
    cvss_score = Column(String, nullable=True)
    normalized_at = Column(DateTime, default=datetime.utcnow)
    artifact = relationship("Artifact", back_populates="findings")