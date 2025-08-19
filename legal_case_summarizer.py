from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import uvicorn
import os
import io
from datetime import datetime

# File handling
from pypdf import PdfReader
from docx import Document as DocxDocument
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# LLM: Ollama (local llama3)
import ollama

app = FastAPI(title="legal case summarizer", version="1.0")

# Allow simple cross-origin use (optional)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------  Frontend ----------
INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Legal Case Summarizer</title>
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#0b0f15;color:#e8eef6}
    .wrap{max-width:880px;margin:40px auto;padding:24px;background:#121826;border:1px solid #1f2633;border-radius:16px;box-shadow:0 10px 30px rgba(0,0,0,.3)}
    h1{margin:0 0 6px;font-size:28px}
    p.mute{color:#9fb0c3;margin-top:4px}
    form{margin-top:18px;border:2px dashed #273245;padding:24px;border-radius:12px}
    input[type=file]{display:block;margin:8px 0 12px;width:100%;color:#e8eef6}
    button{background:#4f46e5;border:none;color:#fff;padding:12px 18px;border-radius:12px;font-size:15px;cursor:pointer}
    button:disabled{opacity:.6;cursor:not-allowed}
    .row{display:flex;gap:12px;align-items:center}
    .out{margin-top:18px;padding:12px;background:#0f1522;border:1px solid #263149;border-radius:12px}
    .hint{font-size:13px;color:#9fb0c3}
    a{color:#8ab4ff}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>⚖️ Legal Case Summarizer</h1>
    <p class="mute">Upload one or more case files (PDF, DOCX, or TXT). The app will analyze with Llama 3 and generate a professional report you can download as TXT or PDF.</p>
    <form id="f" enctype="multipart/form-data">
      <input type="file" id="files" name="files" multiple accept=".pdf,.docx,.txt" required />
      <div class="row">
        <button id="btn" type="submit">Analyze with Llama 3</button>
        <span class="hint">No need for 100% accuracy — it aims for clean, structured output.</span>
      </div>
    </form>
    <div id="out" class="out" style="display:none"></div>
  </div>
<script>
const form = document.getElementById('f');
const out = document.getElementById('out');
const btn = document.getElementById('btn');
form.addEventListener('submit', async (e)=>{
  e.preventDefault();
  const fd = new FormData();
  const files = document.getElementById('files').files;
  for (let i=0;i<files.length;i++){ fd.append('files', files[i]); }
  btn.disabled = true; btn.textContent = 'Analyzing…'; out.style.display='block'; out.innerHTML = 'Running LLM on your files. This may take a moment…';
  try{
    const res = await fetch('/analyze', { method:'POST', body: fd });
    if(!res.ok){ throw new Error('Server error'); }
    const data = await res.json();
    if(data.error){ throw new Error(data.error); }
    out.innerHTML = `
      <div><strong>Done!</strong> Download your report:</div>
      <ul>
        <li>📄 <a href="${data.txt_url}" download>Download TXT</a></li>
        <li>🧾 <a href="${data.pdf_url}" download>Download PDF</a></li>
      </ul>
      <div class="hint">Saved on server as: <code>${data.base_name}</code></div>
    `;
  }catch(err){
    out.innerHTML = '❌ '+err.message;
  }finally{
    btn.disabled = false; btn.textContent = 'Analyze with Llama 3';
  }
});
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)



ALLOWED_EXT = {'.pdf', '.txt', '.docx'}
STORE_DIR = os.path.join(os.path.dirname(__file__), 'outputs')
os.makedirs(STORE_DIR, exist_ok=True)

def read_file(file: UploadFile) -> str:
    name = file.filename or "uploaded"
    _, ext = os.path.splitext(name.lower())
    content = file.file.read()

    if ext not in ALLOWED_EXT:
        return f"\n[Skipped unsupported file: {name}]\n"

    try:
        if ext == '.pdf':
            reader = PdfReader(io.BytesIO(content))
            texts = []
            for page in reader.pages:
                try:
                    texts.append(page.extract_text() or '')
                except Exception:
                    pass
            return f"\n--- BEGIN PDF: {name} ---\n" + "\n".join(texts) + f"\n--- END PDF: {name} ---\n"
        elif ext == '.docx':
            bio = io.BytesIO(content)
            doc = DocxDocument(bio)
            txt = "\n".join(p.text for p in doc.paragraphs)
            return f"\n--- BEGIN DOCX: {name} ---\n{txt}\n--- END DOCX: {name} ---\n"
        else:  # .txt
            try:
                return f"\n--- BEGIN TXT: {name} ---\n{content.decode('utf-8', errors='ignore')}\n--- END TXT: {name} ---\n"
            except Exception:
                return f"\n[Failed to read text file: {name}]\n"
    except Exception as e:
        return f"\n[Error reading {name}: {e}]\n"

PROMPT_TEMPLATE = """
You are a legal analysis AI. You MUST follow the EXACT format below. DO NOT deviate from this structure.

STEP 1: Determine if the documents contain legal case materials (court cases, lawsuits, legal disputes, judgments, pleadings, legal briefs, court orders, legal contracts disputes, etc.)

STEP 2: If documents are NOT legal case materials (receipts, invoices, tickets, personal documents, etc.), write "Not legal case materials" in section 1 and "N/A" for ALL other sections.

STEP 3: If documents ARE legal case materials, analyze them and fill each section.

MANDATORY OUTPUT FORMAT - Copy these headings EXACTLY:

1. 25 Word Summary of the Case including Category of Law
[If not legal case materials, write: "Not legal case materials"]
[If legal case materials, write EXACTLY 25 words summarizing the case and legal category]

2. Name of Plaintiff & Defendant including respective Attorneys representing them
Plaintiff: [Name or N/A] | Attorney: [Name or N/A]
Defendant: [Name or N/A] | Attorney: [Name or N/A]

3. Case Story (Within 500 Words)
[Narrative description of the legal dispute or "N/A"]

4. Key Facts of the Case
• [Fact 1 or N/A]
• [Fact 2 or N/A]
• [Additional facts as bullet points or just • N/A]

5. Claims Made by Plaintiff including evidences/Documents
• [Claim 1 with evidence or N/A]
• [Claim 2 with evidence or N/A]
• [Additional claims as bullet points or just • N/A]

6. Claims Made by Defendant including evidences/Documents
• [Claim 1 with evidence or N/A]
• [Claim 2 with evidence or N/A]
• [Additional claims as bullet points or just • N/A]

7. List of Act, Section, Law and why it is applicable
• [Act/Section - Reason or N/A]
• [Additional acts as bullet points or just • N/A]

8. Procedural History (If Any)
[Chronological procedural events or "N/A"]

9. Comprehensive List of Dates/Chronology of Events
• [DD MMM YYYY - Event description or N/A]
• [Additional dates as bullet points or just • N/A]

CRITICAL RULES FOR LLAMA3:
- Use ONLY the 9 numbered sections above
- Keep the exact heading text
- If not legal case materials, section 1 = "Not legal case materials", all others = "N/A"
- Do NOT add introduction paragraphs
- Do NOT add conclusion paragraphs  
- Do NOT add additional sections
- Do NOT change the numbering
- Start immediately with "1. 25 Word Summary..."
- End immediately after section 9
- Use bullet points (•) where specified
- Write "N/A" when information is missing

Documents to analyze:
"""


def build_prompt_text(all_text: str) -> str:
    MAX_CHARS = 120000
    trimmed = all_text[:MAX_CHARS]
    return PROMPT_TEMPLATE + "\n" + trimmed


def call_llama3(prompt: str) -> str:
    try:
        stream = ollama.chat(
            model='llama3',
            messages=[
                {"role": "system", "content": "You are a precise legal analyst. Output exactly the requested structure."},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )
        content = stream.get('message', {}).get('content', '')
        return content.strip()
    except Exception:
        return "ERROR: LLM server not reachable"


def save_txt(base_path: str, text: str) -> str:
    txt_path = base_path + '.txt'
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(text)
    return txt_path


def save_pdf(base_path: str, text: str) -> str:
    pdf_path = base_path + '.pdf'
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    x = 2.0 * cm
    y = height - 2.0 * cm
    max_width = width - 4.0 * cm

    def draw_wrapped(text_block: str):
        nonlocal y
        for paragraph in text_block.split('\n'):
            lines = wrap_text(paragraph, c, max_width)
            for line in lines:
                if y < 2.0 * cm:
                    c.showPage()
                    y = height - 2.0 * cm
                c.drawString(x, y, line)
                y -= 14
            y -= 6

    def wrap_text(s: str, canv, max_w: float):
        words = s.split(' ')
        wrapped = []
        line = ''
        for w in words:
            test = (line + ' ' + w).strip()
            if canv.stringWidth(test, "Helvetica", 10) <= max_w:
                line = test
            else:
                wrapped.append(line)
                line = w
        if line:
            wrapped.append(line)
        return wrapped

    c.setFont("Helvetica", 10)
    draw_wrapped(text)
    c.save()
    with open(pdf_path, 'wb') as f:
        f.write(buffer.getvalue())
    return pdf_path


@app.post('/analyze')
async def analyze(files: List[UploadFile] = File(...)):
    if not files:
        return JSONResponse({"error": "No files uploaded"}, status_code=400)

    # Combine all uploaded files
    all_texts = []
    safe_names = []
    for f in files:
        safe_names.append(f.filename)
        all_texts.append(read_file(f))
    joined = "\n\n".join(all_texts)

    prompt = build_prompt_text(joined)
    result = call_llama3(prompt)

    if result.startswith("ERROR: LLM server not reachable"):
        return JSONResponse({"error": "LLM server is down. Please ensure Ollama is running with 'llama3' model."}, status_code=500)

    if len(result.strip()) < 30:
        return JSONResponse({"error": "LLM returned empty response."}, status_code=500)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = f"case_report_{timestamp}"
    base_path = os.path.join(STORE_DIR, base)

    txt_path = save_txt(base_path, result)
    pdf_path = save_pdf(base_path, result)

    return {
        "base_name": os.path.basename(base_path),
        "txt_url": f"/download/{os.path.basename(txt_path)}",
        "pdf_url": f"/download/{os.path.basename(pdf_path)}",
        "files_received": safe_names,
    }

@app.get('/download/{fname}')
def download(fname: str):
    path = os.path.join(STORE_DIR, fname)
    if not os.path.isfile(path):
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(path, filename=fname)


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)