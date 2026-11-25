from pydantic import BaseModel
from typing import List, Optional

class ArchitectRequest(BaseModel):
    input_text: str
    action: str  # "blast_radius", "debug", or "review"
    context_chunks: List[str]

class ArchitectResponse(BaseModel):
    report_markdown: str
    confidence_score: float
    affected_files: Optional[List[str]] = []
