import docx
import sys

doc = docx.Document(r"d:\rapidoproject\paper\camera_ready\AI_Powered_Unified_Mobility_DMFE_Camera_Ready_UPDATED.docx")

texts = []
for i, p in enumerate(doc.paragraphs):
    if p.text.strip():
        texts.append(f"{i}: {p.text}")

with open(r"d:\rapidoproject\scratch_read_camera_ready.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(texts))
print(f"Extracted {len(texts)} paragraphs.")
