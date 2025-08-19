Legal Case Summarizer 🏛️

Legal Case Summarizer is a FastAPI-based web application that allows users to upload legal documents in PDF, DOCX, or TXT formats and generates a professionally structured case summary using Llama 3. The generated report can be downloaded as a TXT or PDF file.
The app supports uploading multiple legal case files at once. It reads and extracts the content from the documents and generates structured reports containing a 25-word summary with the category of law, parties and counsel, a concise case story, key facts, plaintiff and defendant claims, applicable laws and rationale, procedural history, and a chronology of events. The frontend is minimal and clean, making it easy to upload files, run the analysis, and download results.
Installation: First, clone the repository and navigate into the folder. Create a Python virtual environment and activate it. Install the required dependencies using pip. Make sure that the Ollama Llama 3 model is installed and running locally, as the app depends on it for summarization.
Usage: Run the FastAPI server with uvicorn legal_case_summarizer:app --reload --host 0.0.0.0 --port 8000 and open http://localhost:8000 in your browser. Upload one or more case files and click “Analyze with Llama 3.” Once processing is complete, you can download the generated TXT or PDF report from the interface.

Project structure:

legal_case_summarizer.py: Main FastAPI application.
outputs/: Folder where generated reports (TXT & PDF) are stored.
requirements.txt: Python dependencies.

README.md: Project documentation.
Dependencies include: FastAPI, Uvicorn, pypdf, python-docx, reportlab, Ollama, and CORSMiddleware for cross-origin support. They can be installed via pip install fastapi uvicorn pypdf python-docx reportlab ollama.
Notes: The app trims uploaded content to 120,000 characters for the AI prompt. If the Ollama server is down or unreachable, the app will return an error. All uploaded files and generated reports are stored temporarily in the outputs/ folder.
This project is open-source and can be modified for educational or personal purposes. It provides an easy, AI-powered solution to analyze legal case files and generate structured, professional summaries for lawyers, students, or legal researchers
