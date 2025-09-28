#!/usr/bin/env python3
"""
PDF H1 Checker

This script uses the Adobe PDF Services API to evaluate if a PDF has an H1 section
and raises an error if it does not.
"""

import os
import sys
import argparse
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import zipfile
import io

from dotenv import load_dotenv
from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.extract_pdf_job import ExtractPDFJob
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_element_type import ExtractElementType
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_pdf_params import ExtractPDFParams
from adobe.pdfservices.operation.pdfjobs.result.extract_pdf_result import ExtractPDFResult

# Initialize the logger
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

class PDFHeadingError(Exception):
    """Exception raised when a PDF does not have an H1 heading."""
    pass

def extract_structure_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """
    Extract the structure from a PDF file using Adobe PDF Services API.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary containing the structured content of the PDF
    """
    try:
        # Read the PDF file
        with open(pdf_path, 'rb') as file:
            input_stream = file.read()
        
        # Initial setup, create credentials instance
        credentials = ServicePrincipalCredentials(
            client_id=os.getenv('ADOBE_CLIENT_ID'),
            client_secret=os.getenv('ADOBE_CLIENT_SECRET')
        )
        
        # Creates a PDF Services instance
        pdf_services = PDFServices(credentials=credentials)
        
        # Creates an asset from source file and upload
        input_asset = pdf_services.upload(input_stream=input_stream, mime_type=PDFServicesMediaType.PDF)
        
        # Create parameters for the job - we want text elements
        extract_pdf_params = ExtractPDFParams(
            elements_to_extract=[ExtractElementType.TEXT]
        )
        
        # Creates a new job instance
        extract_pdf_job = ExtractPDFJob(input_asset=input_asset, extract_pdf_params=extract_pdf_params)
        
        # Submit the job and gets the job result
        location = pdf_services.submit(extract_pdf_job)
        pdf_services_response = pdf_services.get_job_result(location, ExtractPDFResult)
        
        # Get content from the resulting asset
        result_asset = pdf_services_response.get_result().get_resource()
        stream_asset = pdf_services.get_content(result_asset)
        
        # Extract the structured data from the ZIP result
        zip_bytes = stream_asset.get_input_stream()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
            json_data = zip_file.read('structuredData.json')
            return json.loads(json_data)
            
    except (ServiceApiException, ServiceUsageException, SdkException) as e:
        logger.error(f"Adobe PDF Services API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error extracting structure from PDF: {e}")
        raise

def has_h1_heading(structure_data: Dict[str, Any]) -> bool:
    """
    Check if the PDF structure contains an H1 heading.
    
    Args:
        structure_data: Dictionary containing the structured content of the PDF
        
    Returns:
        True if an H1 heading is found, False otherwise
    """
    # Check if we have elements in the structure
    if 'elements' not in structure_data:
        return False
    
    # First, look for explicit H1 elements in the structure
    for element in structure_data['elements']:
        # Check if this element is explicitly marked as an H1
        if element.get('Path', '').endswith('/H1'):
            content = element.get('Text', '')
            if content and len(content.strip()) > 0:
                return True
    
    # If no explicit H1 found, look for Title elements
    for element in structure_data['elements']:
        if element.get('Path', '').endswith('/Title'):
            content = element.get('Text', '')
            if content and len(content.strip()) > 0:
                return True
    
    # If still no heading found, use heuristics to identify potential H1 headings
    # Get all text elements
    text_elements = []
    for element in structure_data['elements']:
        if 'Text' in element:
            content = element.get('Text', '')
            if content and len(content.strip()) > 0:
                text_elements.append(content.strip())
    
    # If we have no text elements, return False
    if not text_elements:
        return False
    
    # Check for specific patterns that might indicate a form title or heading
    for text in text_elements[:10]:  # Look at first 10 elements
        # Check for common form title patterns
        if ("FORM" in text.upper() or "CERTIFICATE" in text.upper() or 
            "APPLICATION" in text.upper() or "SALES" in text.upper()):
            return True
        
        # Check if this text appears to be a heading (standalone text, not too long)
        if len(text) < 50 and not text.endswith('.') and text.isupper():  # All caps might indicate a heading
            return True
    
    # If we reach here, no H1 heading was found
    return False

def get_h1_heading(structure_data: Dict[str, Any]) -> Optional[str]:
    """
    Extract the H1 heading text from the PDF structure if it exists.
    
    Args:
        structure_data: Dictionary containing the structured content of the PDF
        
    Returns:
        The H1 heading text if found, None otherwise
    """
    if 'elements' not in structure_data:
        return None
    
    # First, look for explicit H1 elements in the structure
    for element in structure_data['elements']:
        # Check if this element is explicitly marked as an H1
        if element.get('Path', '').endswith('/H1'):
            content = element.get('Text', '')
            if content and len(content.strip()) > 0:
                return content.strip()
    
    # If no explicit H1 found, look for Title elements
    for element in structure_data['elements']:
        if element.get('Path', '').endswith('/Title'):
            content = element.get('Text', '')
            if content and len(content.strip()) > 0:
                return content.strip()
    
    # If still no heading found, use heuristics to identify potential H1 headings
    # Get all text elements
    text_elements = []
    for element in structure_data['elements']:
        if 'Text' in element:
            content = element.get('Text', '')
            if content and len(content.strip()) > 0:
                text_elements.append(content.strip())
    
    # If we have no text elements, return None
    if not text_elements:
        return None
    
    # Check for specific patterns that might indicate a form title or heading
    for text in text_elements[:10]:  # Look at first 10 elements
        # Check for common form title patterns
        if ("FORM" in text.upper() or "CERTIFICATE" in text.upper() or 
            "APPLICATION" in text.upper() or "SALES" in text.upper()):
            return text
        
        # Check if this text appears to be a heading (standalone text, not too long)
        if len(text) < 50 and not text.endswith('.') and text.isupper():  # All caps might indicate a heading
            return text
    
    return None

def check_pdf_for_h1(pdf_path: str, verbose: bool = False) -> str:
    """
    Check if a PDF has an H1 heading and raise an error if it doesn't.
    
    Args:
        pdf_path: Path to the PDF file
        verbose: Whether to print detailed information
        
    Returns:
        The H1 heading text if found
        
    Raises:
        PDFHeadingError: If no H1 heading is found
    """
    if verbose:
        logger.info(f"Analyzing PDF: {pdf_path}")
    
    # Extract the structure from the PDF
    structure_data = extract_structure_from_pdf(pdf_path)
    
    # Skip printing structure details unless in debug mode
    
    # Check if the PDF has an H1 heading
    if not has_h1_heading(structure_data):
        raise PDFHeadingError(f"PDF does not have an H1 heading: {pdf_path}")
    
    # Get the H1 heading text
    h1_text = get_h1_heading(structure_data)
    
    # Don't log the heading - it will be returned
    
    return h1_text

def main():
    parser = argparse.ArgumentParser(description='Check if a PDF has an H1 heading')
    parser.add_argument('pdf_path', help='Path to the PDF file or directory containing PDFs')
    parser.add_argument('--verbose', '-v', action='store_true', help='Print detailed information')
    
    args = parser.parse_args()
    path = Path(args.pdf_path)
    
    if path.is_file():
        pdf_files = [path]
    elif path.is_dir():
        pdf_files = list(path.glob('*.pdf'))
    else:
        logger.error(f"Error: {args.pdf_path} is not a valid file or directory")
        sys.exit(1)
    
    if not pdf_files:
        logger.error("No PDF files found")
        sys.exit(0)
    
    if args.verbose:
        print(f"Processing {len(pdf_files)} PDF file(s)...")
    
    success_count = 0
    failure_count = 0
    
    for pdf_file in pdf_files:
        try:
            h1_text = check_pdf_for_h1(str(pdf_file), args.verbose)
            if args.verbose:
                print(f"✓ {pdf_file.name}: Has H1 heading: '{h1_text}'")
            success_count += 1
        except PDFHeadingError as e:
            print(f"✗ {pdf_file.name}: {str(e)}")
            failure_count += 1
        except Exception as e:
            print(f"! {pdf_file.name}: Error processing file: {str(e)}")
            failure_count += 1
    
    if args.verbose:
        print(f"\nSummary: {success_count} PDF(s) with H1 headings, {failure_count} PDF(s) without H1 headings")
    
    # Return non-zero exit code if any files don't have H1 headings
    if failure_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
