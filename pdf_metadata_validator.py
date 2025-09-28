#!/usr/bin/env python3
"""
PDF Metadata Validator

This script validates PDF filenames against their H1 headings and suggests
corrections using the OpenAI API if needed.
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import Optional, Tuple, List

import PyPDF2
from dotenv import load_dotenv
import openai

# Load environment variables from .env file
load_dotenv()

# Get API key from environment variable
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("Error: OPENAI_API_KEY environment variable not set.")
    print("Please create a .env file with your API key or set it in your environment.")
    sys.exit(1)

# Initialize OpenAI client
client = openai.OpenAI(api_key=OPENAI_API_KEY)


def extract_h1_from_pdf(pdf_path: str) -> Optional[str]:
    """
    Extract the H1 heading from a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        The H1 heading text if found, None otherwise
    """
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            
            # We'll check the first few pages for an H1 heading
            # This is a simplified approach - real H1 detection would require more sophisticated analysis
            for page_num in range(min(3, len(reader.pages))):
                page = reader.pages[page_num]
                text = page.extract_text()
                
                if not text:
                    continue
                
                # Look for potential H1 headings - this is a simplified approach
                # Real implementation would need to consider font size, styling, etc.
                lines = text.split('\n')
                for line in lines:
                    line = line.strip()
                    # Skip empty lines or very short lines
                    if not line or len(line) < 5:
                        continue
                    
                    # Skip lines that are likely not titles (too long, contain certain patterns)
                    if len(line) > 100 or re.search(r'^\d+\.\s', line):
                        continue
                    
                    # If we find a good candidate for H1, return it
                    return line
                
        # If we couldn't find a clear H1 heading, return None
        return None
    
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return None


def validate_filename(filename: str, h1_heading: str) -> Tuple[bool, str]:
    """
    Validate if the filename contains words from the H1 heading.
    
    Args:
        filename: The filename without extension
        h1_heading: The H1 heading text
        
    Returns:
        Tuple of (is_valid, reason)
    """
    # Convert filename and heading to lowercase for comparison
    filename_lower = filename.lower()
    h1_lower = h1_heading.lower()
    
    # Extract words from the filename and heading
    filename_words = set(re.findall(r'\w+', filename_lower))
    heading_words = set(re.findall(r'\w+', h1_lower))
    
    # Filter out common words that might not be significant
    common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'of', 'for', 'in', 'on', 'to', 'with'}
    heading_words = {word for word in heading_words if word not in common_words and len(word) > 2}
    
    # Check if the filename contains at least some words from the heading
    common_words_count = len(filename_words.intersection(heading_words))
    
    # Check if the filename uses hyphen separation
    has_hyphens = '-' in filename
    
    if common_words_count >= 2 and has_hyphens:
        return True, "Filename matches H1 heading pattern"
    elif not has_hyphens:
        return False, "Filename should use hyphen separation"
    else:
        return False, f"Filename doesn't contain enough words from the H1 heading"


def suggest_filename_with_openai(h1_heading: str, current_filename: str) -> str:
    """
    Use OpenAI API to suggest a better filename based on the H1 heading.
    
    Args:
        h1_heading: The H1 heading text
        current_filename: The current filename
        
    Returns:
        Suggested filename
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            max_tokens=100,
            temperature=0.0,
            messages=[
                {
                    "role": "user",
                    "content": f"""Given the H1 heading from a PDF: "{h1_heading}"
                    
Current filename: "{current_filename}"

Generate a better filename that:
1. Contains key words from the H1 heading
2. Uses hyphen-separation between words
3. Is all lowercase
4. Excludes common words like "the", "and", etc.
5. Is concise but descriptive

Return ONLY the suggested filename without any explanation or additional text."""
                }
            ]
        )
        
        suggested_filename = response.choices[0].message.content.strip()
        # Clean up the suggested filename to ensure it's valid
        suggested_filename = re.sub(r'[^\w\-]', '', suggested_filename)
        return suggested_filename
    
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        # Fallback: create a simple filename from the heading
        words = re.findall(r'\w+', h1_heading.lower())
        words = [w for w in words if len(w) > 2 and w not in {'the', 'and', 'for', 'with'}]
        return "-".join(words[:4])


def main():
    parser = argparse.ArgumentParser(description='Validate PDF filenames against their H1 headings')
    parser.add_argument('pdf_path', help='Path to the PDF file or directory containing PDFs')
    parser.add_argument('--no-rename', action='store_true', help='Do not automatically rename files with invalid names')
    parser.add_argument('--verbose', '-v', action='store_true', help='Print detailed information')
    
    args = parser.parse_args()
    path = Path(args.pdf_path)
    
    if path.is_file():
        pdf_files = [path]
    elif path.is_dir():
        pdf_files = list(path.glob('*.pdf'))
    else:
        print(f"Error: {args.pdf_path} is not a valid file or directory")
        sys.exit(1)
    
    if not pdf_files:
        print("No PDF files found")
        sys.exit(0)
    
    print(f"Processing {len(pdf_files)} PDF file(s)...")
    
    for pdf_file in pdf_files:
        if args.verbose:
            print(f"\nAnalyzing: {pdf_file}")
        
        # Extract H1 heading
        h1_heading = extract_h1_from_pdf(str(pdf_file))
        if not h1_heading:
            print(f"Warning: Could not extract H1 heading from {pdf_file}")
            continue
        
        if args.verbose:
            print(f"Detected H1: {h1_heading}")
        
        # Get current filename without extension
        current_filename = pdf_file.stem
        
        # Validate filename
        is_valid, reason = validate_filename(current_filename, h1_heading)
        
        if is_valid:
            print(f"✓ {pdf_file.name}: Valid filename")
        else:
            print(f"✗ {pdf_file.name}: Invalid filename - {reason}")
            
            # Suggest a better filename
            suggested_filename = suggest_filename_with_openai(h1_heading, current_filename)
            suggested_full_name = f"{suggested_filename}.pdf"
            
            print(f"  Suggested filename: {suggested_full_name}")
            
            # Rename the file unless --no-rename flag is used
            if not args.no_rename:
                new_path = pdf_file.with_name(suggested_full_name)
                try:
                    pdf_file.rename(new_path)
                    print(f"  Renamed to: {suggested_full_name}")
                except Exception as e:
                    print(f"  Error renaming file: {e}")


if __name__ == "__main__":
    main()
