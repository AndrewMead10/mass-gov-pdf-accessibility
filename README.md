# PDF Accessibility Checker

A Python script that uses Adobe PDF Services to check PDF documents for accessibility compliance and generate accessibility reports.

## Features

- Checks PDF files for accessibility issues using Adobe PDF Services
- Generates tagged PDF versions with improved accessibility
- Creates detailed JSON accessibility reports
- Supports checking specific page ranges
- Creates timestamped output directories
- Comprehensive error handling and logging

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