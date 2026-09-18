import docx
import sys

doc = docx.Document(r"d:\rapidoproject\paper\camera_ready\ICCES_Response_to_Reviewers.docx")

texts = []
for i, p in enumerate(doc.paragraphs):
    if p.text.strip():
        texts.append(f"{i}: {p.text}")

with open(r"d:\rapidoproject\scratch_read_responses.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(texts))
print(f"Extracted {len(texts)} paragraphs.")
