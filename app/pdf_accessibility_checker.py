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
import threading
from datetime import datetime
from typing import Dict, Optional, Tuple

from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.pdf_accessibility_checker_job import PDFAccessibilityCheckerJob
from adobe.pdfservices.operation.pdfjobs.result.pdf_accessibility_checker_result import PDFAccessibilityCheckerResult

from app.autotag_pdf import PDFAutotagger

# Initialize the logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

AUTOTAG_OUTPUT_DIR = os.path.join("output_pdfs", "autotagged")

class PDFAccessibilityChecker:
    _autotag_lock = threading.Lock()
    _autotag_cache: Dict[str, Tuple[int, str]] = {}
    _autotag_events: Dict[str, threading.Event] = {}

    def __init__(self, credentials_file: Optional[str] = None) -> None:
        """Initialize with credentials from file or environment variables"""
        if credentials_file and os.path.exists(credentials_file):
            self.credentials = self._load_credentials_from_file(credentials_file)
        else:
            self.credentials = self._load_credentials_from_env()

        self.pdf_services = PDFServices(credentials=self.credentials)
        self.autotagger = PDFAutotagger(credentials=self.credentials)

    def _load_credentials_from_file(self, credentials_file: str) -> ServicePrincipalCredentials:
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

    def _load_credentials_from_env(self) -> ServicePrincipalCredentials:
        """Load credentials from environment variables"""
        client_id = os.getenv('PDF_SERVICES_CLIENT_ID')
        client_secret = os.getenv('PDF_SERVICES_CLIENT_SECRET')

        if not client_id or not client_secret:
            raise ValueError("PDF_SERVICES_CLIENT_ID and PDF_SERVICES_CLIENT_SECRET environment variables must be set")

        return ServicePrincipalCredentials(client_id=client_id, client_secret=client_secret)

    def _prepare_pdf(self, pdf_file_path: str) -> str:
        """Run autotagging (once per input) and return the path used for checks."""
        resolved_path = os.path.abspath(pdf_file_path)
        try:
            source_stat = os.stat(resolved_path)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"PDF file not found: {pdf_file_path}") from exc

        cache_key = resolved_path
        source_mtime_ns = source_stat.st_mtime_ns

        while True:
            with self._autotag_lock:
                cached_entry = self._autotag_cache.get(cache_key)
                if cached_entry and cached_entry[0] == source_mtime_ns and os.path.exists(cached_entry[1]):
                    return cached_entry[1]

                wait_event = self._autotag_events.get(cache_key)
                if wait_event is None:
                    wait_event = threading.Event()
                    self._autotag_events[cache_key] = wait_event
                    break

            wait_event.wait()

        try:
            os.makedirs(AUTOTAG_OUTPUT_DIR, exist_ok=True)
            base_name = os.path.splitext(os.path.basename(resolved_path))[0]
            output_path = os.path.join(AUTOTAG_OUTPUT_DIR, f"{base_name}_autotagged.pdf")

            autotag_result = self.autotagger.autotag_pdf(
                input_path=resolved_path,
                output_path=output_path,
            )

            prepared_path = resolved_path
            if autotag_result.get("success"):
                candidate_path = autotag_result.get("output_path") or output_path
                if candidate_path and os.path.exists(candidate_path):
                    prepared_path = candidate_path
                else:
                    logger.warning(
                        "Autotagging reported success but output missing for %s; using original",
                        resolved_path,
                    )
            else:
                logger.warning(
                    "Autotagging failed for %s: %s",
                    resolved_path,
                    autotag_result.get("message", "unknown error"),
                )

            with self._autotag_lock:
                self._autotag_cache[cache_key] = (source_mtime_ns, prepared_path)

            return prepared_path
        finally:
            with self._autotag_lock:
                event = self._autotag_events.pop(cache_key, None)
            if event:
                event.set()

    def check_accessibility(
        self,
        pdf_file_path: str,
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
        save_tagged_pdf: bool = True,
    ) -> dict:
        """
        Check accessibility of a PDF file

        Args:
            pdf_file_path (str): Path to the PDF file to check
            page_start (int, optional): Starting page for accessibility check
            page_end (int, optional): Ending page for accessibility check

        Returns:
            dict: Contains the tagged PDF path and accessibility report JSON
        """
        try:
            original_abs_path = os.path.abspath(pdf_file_path)
            prepared_pdf_path = self._prepare_pdf(pdf_file_path)
            prepared_abs_path = os.path.abspath(prepared_pdf_path)

            logger.info(f"Starting accessibility check for: {pdf_file_path}")
            if prepared_abs_path != original_abs_path:
                logger.info(f"Using autotagged intermediate PDF: {prepared_pdf_path}")

            # Read the PDF file
            with open(prepared_pdf_path, 'rb') as pdf_file:
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

            # Get the binary data
            tagged_pdf_data = stream_asset.get_input_stream()
            accessibility_report_data = stream_report.get_input_stream()

            # Create output_pdfs directory if it doesn't exist
            output_pdfs_dir = "output_pdfs"
            os.makedirs(output_pdfs_dir, exist_ok=True)

            # Generate output filename for tagged PDF
            base_filename = os.path.splitext(os.path.basename(original_abs_path))[0]
            timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            tagged_pdf_filename = f"{base_filename}_tagged_{timestamp}.pdf"
            tagged_pdf_path = os.path.join(output_pdfs_dir, tagged_pdf_filename)

            if save_tagged_pdf:
                # Save the tagged PDF to output_pdfs folder
                with open(tagged_pdf_path, "wb") as file:
                    file.write(tagged_pdf_data)
                logger.info(f"Accessibility check completed successfully")
                logger.info(f"Tagged PDF saved to: {tagged_pdf_path}")
            else:
                # When not saving, clear the path to avoid confusion
                tagged_pdf_path = None
                logger.info(f"Accessibility check completed (report only for pages {page_start}-{page_end})")

            autotagged_pdf_path = None
            if prepared_abs_path != original_abs_path:
                autotagged_pdf_path = prepared_pdf_path

            return {
                'tagged_pdf_path': tagged_pdf_path,
                'accessibility_report_json': json.loads(accessibility_report_data.decode('utf-8')),
                'source_pdf_path': original_abs_path,
                'autotagged_pdf_path': autotagged_pdf_path,
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
            page_start=args.page_start,
            page_end=args.page_end
        )

        # Create output directory for CLI usage
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        base_filename = os.path.splitext(os.path.basename(args.pdf_file))[0]
        output_subdir = os.path.join(args.output, f"{base_filename}_{timestamp}")
        os.makedirs(output_subdir, exist_ok=True)

        # Save/copy the tagged PDF into the CLI output directory
        pdf_output_path = os.path.join(output_subdir, f"{base_filename}_tagged.pdf")
        if result['tagged_pdf_path'] and os.path.exists(result['tagged_pdf_path']):
            import shutil
            shutil.copyfile(result['tagged_pdf_path'], pdf_output_path)

        # Save the accessibility report JSON into the CLI output directory
        json_output_path = os.path.join(output_subdir, f"{base_filename}_accessibility_report.json")
        with open(json_output_path, "w", encoding="utf-8") as file:
            json.dump(result['accessibility_report_json'], file, ensure_ascii=False, indent=2)

        print(f"\n✅ Accessibility check completed successfully!")
        if os.path.exists(pdf_output_path):
            print(f"📄 Tagged PDF: {pdf_output_path}")
        print(f"📊 Accessibility Report: {json_output_path}")
        print(f"📁 Output Directory: {output_subdir}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
