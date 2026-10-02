"""Pull skills out of an uploaded résumé (PDF, DOCX or TXT). Runs in memory only."""

from __future__ import annotations

import io
import re
import zipfile

SKILLS = [
    "python", "java", "c++", "c#", "golang", "rust", "javascript", "typescript", "sql", "scala", "kotlin",
    "swift", "matlab", "react", "node", "next.js", "django", "flask", "fastapi", "spring",
    "pytorch", "tensorflow", "jax", "keras", "scikit-learn", "pandas", "numpy", "spark", "hadoop", "airflow",
    "kafka", "docker", "kubernetes", "aws", "gcp", "azure", "linux", "git", "graphql", "postgres", "mysql",
    "mongodb", "redis", "llm", "nlp", "computer vision", "deep learning", "machine learning",
    "reinforcement learning", "transformers", "hugging face", "langchain", "rag", "statistics",
    "data analysis", "tableau", "excel", "backend", "frontend", "distributed systems", "microservices",
]


def extract_text(name: str, data: bytes) -> str:
    name = name.lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
        except Exception:
            return ""
    if name.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml").decode("utf8", "ignore")
            return re.sub(r"<[^>]+>", " ", xml)
        except Exception:
            return ""
    return data.decode("utf8", "ignore")


def find_skills(text: str) -> list[str]:
    low = f" {text.lower()} "
    found = []
    for s in SKILLS:
        if re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9+#])", low):
            found.append(s)
    return found
