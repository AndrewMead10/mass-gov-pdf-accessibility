#!/usr/bin/env python3
"""
PDF Autotagging Script

This script automatically adds accessibility tags to PDF files using Adobe PDF Services API.
It can process single files or entire directories and includes options for generating
accessibility reports and configuring tagging parameters.
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.autotag_pdf_job import AutotagPDFJob
from adobe.pdfservices.operation.pdfjobs.params.autotag_pdf.autotag_pdf_params import AutotagPDFParams
from adobe.pdfservices.operation.pdfjobs.result.autotag_pdf_result import AutotagPDFResult

# Initialize the logger
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

class PDFAutotagger:
    """
    A class to handle PDF autotagging operations using Adobe PDF Services API.
    """
    
    def __init__(self):
        """Initialize the PDFAutotagger with default values."""
        self.credentials = ServicePrincipalCredentials(
            client_id=os.getenv('ADOBE_CLIENT_ID'),
            client_secret=os.getenv('ADOBE_CLIENT_SECRET')
        )
        self.pdf_services = PDFServices(credentials=self.credentials)
        
    def autotag_pdf(self, input_path: str, output_path: Optional[str] = None, 
                    generate_report: bool = False, shift_headings: bool = False) -> dict:
        """
        Add accessibility tags to a PDF file.
        
        Args:
            input_path: Path to the input PDF file
            output_path: Path where to save the tagged PDF (optional)
            generate_report: Whether to generate an accessibility report
            shift_headings: Whether to shift headings in the document
            
        Returns:
            Dictionary with results of the operation
        """
        try:
            # Determine output path if not provided
            if not output_path:
                input_file_path = Path(input_path)
                output_path = str(input_file_path.with_name(f"{input_file_path.stem}_tagged{input_file_path.suffix}"))
            
            # Create output directory if it doesn't exist
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            # Read the input PDF
            with open(input_path, 'rb') as file:
                input_stream = file.read()
            
            # Upload the PDF to Adobe's services
            input_asset = self.pdf_services.upload(
                input_stream=input_stream,
                mime_type=PDFServicesMediaType.PDF
            )
            
            # Create parameters for the autotagging job
            autotag_params = AutotagPDFParams(
                shift_headings=shift_headings,
                generate_report=generate_report
            )
            
            # Create and submit the job
            autotag_job = AutotagPDFJob(
                input_asset=input_asset,
                autotag_pdf_params=autotag_params
            )
            
            logger.info(f"Submitting autotagging job for {input_path}...")
            location = self.pdf_services.submit(autotag_job)
            pdf_services_response = self.pdf_services.get_job_result(location, AutotagPDFResult)
            
            # Get and save the tagged PDF
            result_asset: CloudAsset = pdf_services_response.get_result().get_tagged_pdf()
            stream_asset: StreamAsset = self.pdf_services.get_content(result_asset)
            
            with open(output_path, "wb") as file:
                file.write(stream_asset.get_input_stream())
            
            result = {
                "success": True,
                "input_path": input_path,
                "output_path": output_path,
                "message": "PDF successfully tagged"
            }
            
            # Generate and save report if requested
            if generate_report:
                report_path = f"{Path(output_path).stem}_report.xlsx"
                result_asset_report: CloudAsset = pdf_services_response.get_result().get_report()
                stream_asset_report: StreamAsset = self.pdf_services.get_content(result_asset_report)
                
                with open(report_path, "wb") as file:
                    file.write(stream_asset_report.get_input_stream())
                
                result["report_path"] = report_path
                result["message"] += " with accessibility report"
            
            return result
            
        except (ServiceApiException, ServiceUsageException, SdkException) as e:
            logger.error(f"Adobe PDF Services API error: {e}")
            return {
                "success": False,
                "input_path": input_path,
                "message": f"Error autotagging PDF: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Error processing {input_path}: {e}")
            return {
                "success": False,
                "input_path": input_path,
                "message": f"Error processing PDF: {str(e)}"
            }


def process_pdfs(pdf_paths: List[str], output_dir: Optional[str] = None, 
                generate_report: bool = False, shift_headings: bool = False) -> List[dict]:
    """
    Process multiple PDF files for autotagging.
    
    Args:
        pdf_paths: List of paths to PDF files
        output_dir: Directory where to save tagged PDFs (optional)
        generate_report: Whether to generate accessibility reports
        shift_headings: Whether to shift headings in the documents
        
    Returns:
        List of dictionaries with results for each PDF
    """
    autotagger = PDFAutotagger()
    results = []
    
    for pdf_path in pdf_paths:
        # Determine output path
        if output_dir:
            input_file = Path(pdf_path)
            output_path = os.path.join(output_dir, f"{input_file.stem}_tagged{input_file.suffix}")
        else:
            input_file = Path(pdf_path)
            output_path = str(input_file.with_name(f"{input_file.stem}_tagged{input_file.suffix}"))
        
        # Process the PDF
        result = autotagger.autotag_pdf(
            input_path=pdf_path,
            output_path=output_path,
            generate_report=generate_report,
            shift_headings=shift_headings
        )
        
        results.append(result)
    
    return results

def main():
    """Main function to parse arguments and process PDFs."""
    parser = argparse.ArgumentParser(description='Add accessibility tags to PDF files')
    parser.add_argument('pdf_path', help='Path to the PDF file or directory containing PDFs')
    parser.add_argument('--output-dir', '-o', help='Directory where tagged PDFs should be saved')
    parser.add_argument('--report', '-r', action='store_true', 
                        help='Generate accessibility reports (in XLSX format)')
    parser.add_argument('--shift-headings', '-s', action='store_true',
                        help='Shift headings in the document structure')
    parser.add_argument('--verbose', '-v', action='store_true', 
                        help='Print detailed information')
    
    args = parser.parse_args()
    
    # Set logging level based on verbosity
    if args.verbose:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)
    
    # Determine input files
    path = Path(args.pdf_path)
    if path.is_file():
        pdf_files = [str(path)]
    elif path.is_dir():
        pdf_files = [str(p) for p in path.glob('*.pdf')]
    else:
        logger.error(f"Error: {args.pdf_path} is not a valid file or directory")
        sys.exit(1)
    
    if not pdf_files:
        logger.error("No PDF files found")
        sys.exit(0)
    
    # Create output directory if specified
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
    
    # Process the PDFs
    print(f"Processing {len(pdf_files)} PDF file(s)...")
    results = process_pdfs(
        pdf_paths=pdf_files,
        output_dir=args.output_dir,
        generate_report=args.report,
        shift_headings=args.shift_headings
    )
    
    # Print results
    success_count = sum(1 for r in results if r["success"])
    failure_count = len(results) - success_count
    
    for result in results:
        if result["success"]:
            print(f"✓ {Path(result['input_path']).name}: {result['message']}")
        else:
            print(f"✗ {Path(result['input_path']).name}: {result['message']}")
    
    print(f"\nSummary: Successfully tagged {success_count} PDF(s)")
    if failure_count > 0:
        print(f"Failed to process {failure_count} PDF(s)")
    
    # Return non-zero exit code if any files failed
    if failure_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
