---

# 📄 PDF Table of Contents Extractor(round1a)

Extract clean, structured table of contents from PDF documents with high accuracy. Processes multiple PDFs in parallel and outputs standardized JSON files.

## Quick Start (Docker)

### Prerequisites

#### Windows

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. Enable WSL 2 backend in Docker Desktop settings
3. Open PowerShell or Windows Terminal

#### macOS

```bash
# Install Homebrew if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Docker
brew install --cask docker
```

#### Linux (Ubuntu/Debian)

```bash
# Install Docker
sudo apt update
sudo apt install docker.io
sudo systemctl enable --now docker

# Add user to docker group (optional)
sudo usermod -aG docker $USER
```

### 1. Clone the Repository

```bash
git clone https://github.com/codehat01/Adobe_round1a
cd Adobe_round1a
```

### 2. Build the Image

```powershell
# From the project root folder
docker build --platform linux/amd64 -t pdf-toc-extractor .
```

### 3. Prepare Your Files

```powershell
# Create input/output folders
mkdir input output

# Copy PDFs into input folder
# Example: copy C:\path\to\your\*.pdf .\input\
```

### 4. Run the Extractor

```powershell
docker run --rm `
  -v ${PWD}\input:/app/input:ro `
  -v ${PWD}\output:/app/output `
  --network none `
  pdf-toc-extractor
```

### 5. Check Results

Find your JSON files in the `output` folder:

```powershell
# List all generated files
Get-ChildItem .\output\*.json

# View a sample output
Get-Content .\output\your_file.json | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

---

## Features

*  **Fast Processing**: Leverages all CPU cores for parallel PDF extraction
*  **High Accuracy**: Detects hierarchical headings (H1, H2, etc.) with precision
*  **Reliable Output**: Schema-validated JSON ensures consistency
*  **Offline Ready**: No internet needed during execution
*  **Lightweight**: Minimal dependencies, compact Docker image

---

## Output Format

Each PDF generates a JSON file like this:

```json
{
  "title": "Document Title",
  "outline": [
    {
      "level": "H1",
      "text": "Chapter 1",
      "page": 1
    },
    {
      "level": "H2",
      "text": "Section 1.1",
      "page": 2
    }
  ],
  "metadata": {
    "page_count": 10,
    "processed_at": "2025-07-27T16:30:45Z"
  }
}
```

---

##  Inspecting Container Output

To directly inspect the output inside the container:

```powershell
# Windows PowerShell
docker run --rm -it `
  -v ${PWD}\input:/app/input:ro `
  -v ${PWD}\output:/app/output `
  --entrypoint /bin/bash `
  pdf-toc-extractor

# Inside container:
ls -la /app/output/          # List output files
cat /app/output/file01.json  # View specific file
cat /app/pdf_processor.log   # View logs
```

---

##  Troubleshooting

###  No output files?

* Ensure PDFs are placed in the `input` directory
* Docker must have write permission to `output`
* Run interactively or check logs for insights

### Slow performance?

* Large PDFs take more time
* All CPU cores are used by default; reduce with `--workers` if needed

---

## Logs

Logs are saved inside the container at `/app/pdf_processor.log`. To save logs to your machine:

```powershell
# Add this to your Docker run command:
-v ${PWD}/logs:/app/logs
```

---

##  Local Installation (Without Docker)

### Prerequisites

* Python 3.10+
* `pip` package manager

### Windows

```powershell
# Clone the repository
git clone https://github.com/codehat01/Adobe_round1a
cd Adobe_round1a

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Linux/macOS

```bash
# Clone the repository
git clone https://github.com/codehat01/Adobe_round1a
cd Adobe_round1a

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Usage

### Batch Process PDFs

```bash
python pdf_processor.py --input-dir input --output-dir output
```

### Process a Single PDF

```bash
python pdf_processor.py --input-file input/document.pdf --output-dir output
```

### Command Line Options

```
--input-dir     Directory containing PDFs (default: ./input)
--input-file    Process single PDF file
--output-dir    Output directory for JSON files (default: ./output)
--workers       Number of worker processes (default: CPU count - 1)
--log-level     Logging level (debug, info, warning, error)
```

---

##  Tech Stack

* **Python**: 3.10+
* **Libraries**:

  * `PyMuPDF`: Extract text and page structure
  * `jsonschema`: Validate JSON output
  * `tqdm`: Progress bars for batch processing

---

## 📄 License

MIT License — free for personal, academic, and commercial use.

---
