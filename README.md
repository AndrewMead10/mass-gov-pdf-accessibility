# PDF Accessibility Checker

A Python script that uses Adobe PDF Services to check PDF documents for accessibility compliance and generate accessibility reports.

## Features

- Checks PDF files for accessibility issues using Adobe PDF Services
- Generates tagged PDF versions with improved accessibility
- Creates detailed JSON accessibility reports
- Supports checking specific page ranges
- Creates timestamped output directories
- Comprehensive error handling and logging
- Extensible identify/resolve pipeline framework for Adobe findings and custom checks

## Prerequisites

- Python 3.6 or higher
- Adobe PDF Services API credentials
- Internet connection for API access

## Setup

### 1. Install Dependencies

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 2. Configure Credentials

The script will automatically look for credentials in one of two locations:

**Option 1: Credentials File (Recommended)**
- Place your credentials in `pdfservices-api-credentials.json`
- Format:
```json
{
  "client_credentials": {
    "client_id": "your_client_id_here",
    "client_secret": "your_client_secret_here"
  },
  "service_principal_credentials": {
    "organization_id": "your_organization_id_here"
  }
}
```

**Option 2: Environment Variables**
- Set environment variables:
```bash
export PDF_SERVICES_CLIENT_ID="your_client_id_here"
export PDF_SERVICES_CLIENT_SECRET="your_client_secret_here"
```

## Usage

### Basic Usage

```bash
# Activate virtual environment
source .venv/bin/activate

# Check a PDF file
python pdf_accessibility_checker.py your_document.pdf
```

### Advanced Options

```bash
# Specify custom credentials file
python pdf_accessibility_checker.py your_document.pdf --credentials /path/to/credentials.json

# Specify output directory
python pdf_accessibility_checker.py your_document.pdf --output results

# Check specific page range
python pdf_accessibility_checker.py your_document.pdf --page-start 1 --page-end 5

# Enable verbose logging
python pdf_accessibility_checker.py your_document.pdf --verbose

# Show help
python pdf_accessibility_checker.py --help
```

### Web Application

To run the web application:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the web application
python -m app.main
```

The web application will be available at `http://localhost:8000`

## Pipeline Framework

The app now includes a pipeline framework under `app/pipelines` that layers on top of the Adobe accessibility report and the per-page results stored in the database. Each pipeline focuses on a single category of issues and can optionally ship with an automatic fix-up step.

- `app/pipelines/base.py` defines the abstract `BasePipeline` contract along with dataclasses (`PipelineContext`, `IdentifyResult`, `ResolveResult`, etc.) used during execution.
- `app/pipelines/helpers.py` contains shared utilities for reading PDFs, walking the Adobe report, and serialising findings.
- `app/pipelines/__init__.py` automatically discovers any subclasses of `BasePipeline` placed in the `app/pipelines` package.
- `app/pipelines/manager.py` exposes `PipelineManager`, which orchestrates running all registered pipelines and handling optional resolve steps.
- Each pipeline module begins with concise "Check / Why / Resolve" comments so reviewers understand the intent and any automated remediation at a glance.

### Implementing a pipeline

1. Create a new file in `app/pipelines/` and subclass `BasePipeline`.
2. Implement `identify(self, context)` to return an `IdentifyResult` instance with one `IdentifyFinding` per accessibility issue found. Include the Adobe issue code, a human-readable summary, and the impacted page numbers.
3. (Optional) Implement `resolve(self, context, identify)` to produce a remediated PDF and describe the changes via `ResolveResult`.

Pipelines have access to:

- The original PDF path and tagged output path.
- The full document-level Adobe accessibility report and all stored per-page reports.
- A document-specific output directory for saving resolved PDFs or debugging artifacts.

### Execution and storage

- `process_pdf_background` runs the pipeline manager after the base Adobe processing finishes.
- Results are stored in two new tables: `pipeline_runs` (metadata for each pipeline execution) and `pipeline_issues` (individual findings).
- Set `PIPELINES_ATTEMPT_RESOLVE=true` to allow automatic resolve steps to run; otherwise only identify steps execute.

### Accessing pipeline data

- Document listings now include a `pipeline_runs_count` field. Detailed document responses include the full run history and findings.
- A dedicated endpoint `GET /api/documents/{document_id}/pipelines` returns all stored runs for a document, including serialized identify/resolve payloads and issue records.

## Docker Deployment

### Using Docker Compose (Recommended)

1. **Build and run with Docker Compose:**
   ```bash
   docker-compose up --build
   ```

2. **Run in detached mode:**
   ```bash
   docker-compose up -d --build
   ```

3. **Stop the application:**
   ```bash
   docker-compose down
   ```

### Using Docker directly

1. **Build the Docker image:**
   ```bash
   docker build -t pdf-accessibility-checker .
   ```

2. **Run the container:**
   ```bash
   docker run -p 8000:8000 \
     -v ./input_pdfs:/app/input_pdfs \
     -v ./output_pdfs:/app/output_pdfs \
     -v ./pdf_accessibility.db:/app/pdf_accessibility.db \
     -v ./pdfservices-api-credentials.json:/app/pdfservices-api-credentials.json \
     pdf-accessibility-checker
   ```

3. **Run in detached mode:**
   ```bash
   docker run -d -p 8000:8000 \
     -v ./input_pdfs:/app/input_pdfs \
     -v ./output_pdfs:/app/output_pdfs \
     -v ./pdf_accessibility.db:/app/pdf_accessibility.db \
     -v ./pdfservices-api-credentials.json:/app/pdfservices-api-credentials.json \
     --name pdf-checker \
     pdf-accessibility-checker
   ```

### Docker Prerequisites

- Docker and Docker Compose installed
- Credentials file `pdfservices-api-credentials.json` in the project root
- Create directories for volumes:
  ```bash
  mkdir -p input_pdfs output_pdfs
  ```

The Docker setup includes:
- Health checks to monitor application status
- Persistent volumes for PDF files and database
- Automatic restart unless stopped manually
- Port 8000 exposed for web access

## Output

The script creates a timestamped output directory containing:

- **Tagged PDF**: `{filename}_tagged.pdf` - The original PDF with improved accessibility tagging
- **Accessibility Report**: `{filename}_accessibility_report.json` - Detailed report of accessibility issues found
- **Output Directory**: `{filename}_{timestamp}/` - Organized output folder

Example output structure:
```
output/
└── YourDocument_2025-09-28T13-46-30/
    ├── YourDocument_tagged.pdf
    └── YourDocument_accessibility_report.json
```

## Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `pdf_file` | | Path to the PDF file to check (required) |
| `--credentials` | `-c` | Path to credentials JSON file (default: pdfservices-api-credentials.json) |
| `--output` | `-o` | Output directory (default: output) |
| `--page-start` | | Starting page for accessibility check (optional) |
| `--page-end` | | Ending page for accessibility check (optional) |
| `--verbose` | `-v` | Enable verbose logging |
| `--help` | `-h` | Show help message |

## Example

```bash
# Check a PDF with verbose output
python pdf_accessibility_checker.py TY2024FilingSeasonResources.pdf --verbose

# Expected output:
# ✅ Accessibility check completed successfully!
# 📄 Tagged PDF: output/TY2024FilingSeasonResources_2025-09-28T13-46-30/TY2024FilingSeasonResources_tagged.pdf
# 📊 Accessibility Report: output/TY2024FilingSeasonResources_2025-09-28T13-46-30/TY2024FilingSeasonResources_accessibility_report.json
# 📁 Output Directory: output/TY2024FilingSeasonResources_2025-09-28T13-46-30
```

## Troubleshooting

### Common Issues

1. **ModuleNotFoundError**: Make sure you've activated the virtual environment
   ```bash
   source .venv/bin/activate
   ```

2. **Credentials Error**: Verify your credentials file exists and contains valid API credentials

3. **Network Issues**: Ensure you have internet access for Adobe PDF Services API calls

4. **File Not Found**: Double-check the PDF file path exists

### Error Messages

- **"Client ID and client secret not found in credentials file"**: Check your credentials file format
- **"PDF_SERVICES_CLIENT_ID and PDF_SERVICES_CLIENT_SECRET environment variables must be set"**: Set environment variables or use credentials file
- **"PDF file not found"**: Verify the input PDF file path

## License

This project uses the Adobe PDF Services SDK. Please refer to Adobe's license terms for the SDK usage.

## Adobe PDF Services Documentation

- [Adobe PDF Services API Documentation](https://developer.adobe.com/document-services/docs/)
- [Accessibility Checker API Reference](https://developer.adobe.com/document-services/docs/pdf-services/api-reference/tag-pdf/#pdf-accessibility-checker)
