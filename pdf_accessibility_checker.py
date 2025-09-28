#!/usr/bin/env python3
"""
PDF Accessibility Checker using Adobe PDF Services
Takes a PDF file path as input and generates accessibility reports.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.pdf_accessibility_checker_job import PDFAccessibilityCheckerJob
from adobe.pdfservices.operation.pdfjobs.result.pdf_accessibility_checker_result import PDFAccessibilityCheckerResult

# Initialize the logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PDFAccessibilityChecker:
    def __init__(self, credentials_file=None):
        """Initialize with credentials from file or environment variables"""
        if credentials_file and os.path.exists(credentials_file):
            self.credentials = self._load_credentials_from_file(credentials_file)
        else:
            self.credentials = self._load_credentials_from_env()

        self.pdf_services = PDFServices(credentials=self.credentials)

    def _load_credentials_from_file(self, credentials_file):
        """Load credentials from JSON file"""
        try:
            with open(credentials_file, 'r') as f:
                creds = json.load(f)

            client_id = creds.get('client_credentials', {}).get('client_id')
            client_secret = creds.get('client_credentials', {}).get('client_secret')

            if not client_id or not client_secret:
                raise ValueError("Client ID and client secret not found in credentials file")

            return ServicePrincipalCredentials(client_id=client_id, client_secret=client_secret)
        except Exception as e:
            logger.error(f"Error loading credentials from file: {e}")
            raise

    def _load_credentials_from_env(self):
        """Load credentials from environment variables"""
        client_id = os.getenv('PDF_SERVICES_CLIENT_ID')
        client_secret = os.getenv('PDF_SERVICES_CLIENT_SECRET')

        if not client_id or not client_secret:
            raise ValueError("PDF_SERVICES_CLIENT_ID and PDF_SERVICES_CLIENT_SECRET environment variables must be set")

        return ServicePrincipalCredentials(client_id=client_id, client_secret=client_secret)

    def check_accessibility(self, pdf_file_path, output_dir="output", page_start=None, page_end=None):
        """
        Check accessibility of a PDF file

        Args:
            pdf_file_path (str): Path to the PDF file to check
            output_dir (str): Directory to save output files
            page_start (int, optional): Starting page for accessibility check
            page_end (int, optional): Ending page for accessibility check

        Returns:
            dict: Paths to the generated PDF and JSON reports
        """
        if not os.path.exists(pdf_file_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_file_path}")

        try:
            logger.info(f"Starting accessibility check for: {pdf_file_path}")

            # Read the PDF file
            with open(pdf_file_path, 'rb') as pdf_file:
                input_stream = pdf_file.read()

            # Create asset from source file and upload
            input_asset = self.pdf_services.upload(input_stream=input_stream, mime_type=PDFServicesMediaType.PDF)

            # Create job with optional page range
            if page_start is not None and page_end is not None:
                from adobe.pdfservices.operation.pdfjobs.params.pdf_accessibility_checker.pdf_accessibility_checker_params import \
                    PDFAccessibilityCheckerParams

                pdf_accessibility_checker_params = PDFAccessibilityCheckerParams(
                    page_start=page_start, page_end=page_end
                )
                pdf_accessibility_checker_job = PDFAccessibilityCheckerJob(
                    input_asset=input_asset,
                    pdf_accessibility_checker_params=pdf_accessibility_checker_params
                )
                logger.info(f"Checking pages {page_start} to {page_end}")
            else:
                pdf_accessibility_checker_job = PDFAccessibilityCheckerJob(input_asset=input_asset)
                logger.info("Checking all pages")

            # Submit the job and get the result
            location = self.pdf_services.submit(pdf_accessibility_checker_job)
            pdf_services_response = self.pdf_services.get_job_result(location, PDFAccessibilityCheckerResult)

            # Get content from the resulting assets
            result_asset: CloudAsset = pdf_services_response.get_result().get_asset()
            stream_asset: StreamAsset = self.pdf_services.get_content(result_asset)

            report_asset: CloudAsset = pdf_services_response.get_result().get_report()
            stream_report: StreamAsset = self.pdf_services.get_content(report_asset)

            # Create output directory
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            base_filename = os.path.splitext(os.path.basename(pdf_file_path))[0]
            output_subdir = os.path.join(output_dir, f"{base_filename}_{timestamp}")
            os.makedirs(output_subdir, exist_ok=True)

            # Save the tagged PDF
            pdf_output_path = os.path.join(output_subdir, f"{base_filename}_tagged.pdf")
            with open(pdf_output_path, "wb") as file:
                file.write(stream_asset.get_input_stream())

            # Save the accessibility report
            json_output_path = os.path.join(output_subdir, f"{base_filename}_accessibility_report.json")
            with open(json_output_path, "wb") as file:
                file.write(stream_report.get_input_stream())

            logger.info(f"Accessibility check completed successfully")
            logger.info(f"Tagged PDF saved to: {pdf_output_path}")
            logger.info(f"Accessibility report saved to: {json_output_path}")

            return {
                'tagged_pdf': pdf_output_path,
                'accessibility_report': json_output_path,
                'output_directory': output_subdir
            }

        except (ServiceApiException, ServiceUsageException, SdkException) as e:
            logger.error(f'Error during accessibility check: {e}')
            raise

def main():
    parser = argparse.ArgumentParser(description='Check PDF accessibility using Adobe PDF Services')
    parser.add_argument('pdf_file', help='Path to the PDF file to check')
    parser.add_argument('--credentials', '-c', help='Path to credentials JSON file',
                       default='pdfservices-api-credentials.json')
    parser.add_argument('--output', '-o', help='Output directory', default='output')
    parser.add_argument('--page-start', type=int, help='Starting page for accessibility check')
    parser.add_argument('--page-end', type=int, help='Ending page for accessibility check')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        checker = PDFAccessibilityChecker(credentials_file=args.credentials)
        result = checker.check_accessibility(
            pdf_file_path=args.pdf_file,
            output_dir=args.output,
            page_start=args.page_start,
            page_end=args.page_end
        )

        print(f"\n✅ Accessibility check completed successfully!")
        print(f"📄 Tagged PDF: {result['tagged_pdf']}")
        print(f"📊 Accessibility Report: {result['accessibility_report']}")
        print(f"📁 Output Directory: {result['output_directory']}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()