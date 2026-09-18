import os
from docx import Document

docx_path = r"d:\rapidoproject\paper\v3_DFME_Final\AI_Powered_Unified_Mobility_DFME_IEEE_Final.docx"
doc = Document(docx_path)

out_text = []
for p in doc.paragraphs:
    if p.text.strip():
        out_text.append(p.text)

with open(r"d:\rapidoproject\scratch_read_docx.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out_text))

print(f"Extracted {len(out_text)} paragraphs.")
