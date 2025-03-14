#!/usr/bin/env python3
"""
Cross-platform runner for Google Maps Scraper
This script automatically detects the operating system and sets up the environment accordingly.
"""

import os
import sys
import platform
import argparse
import subprocess
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("GoogleMapsScraper")

def setup_environment():
    """Set up the environment based on the operating system"""
    system = platform.system().lower()
    logger.info(f"Detected operating system: {system}")
    
    # Create results directory if it doesn't exist
    os.makedirs("results", exist_ok=True)
    
    # Handle platform-specific setup
    if system == "windows":
        # Windows-specific setup
        os.environ["PATH"] = os.path.join(os.getcwd(), "drivers") + os.pathsep + os.environ.get("PATH", "")
    elif system == "darwin":
        # macOS-specific setup
        os.environ["PATH"] = os.path.join(os.getcwd(), "drivers") + os.pathsep + os.environ.get("PATH", "")
    elif system == "linux":
        # Linux-specific setup
        os.environ["PATH"] = os.path.join(os.getcwd(), "drivers") + os.pathsep + os.environ.get("PATH", "")
        os.environ["DISPLAY"] = os.environ.get("DISPLAY", ":0")
    
    # Set common environment variables
    os.environ["PYTHONIOENCODING"] = "utf-8"
    
    return system

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Google Maps Scraper")
    parser.add_argument("--url", type=str, help="Google Maps URL to scrape")
    parser.add_argument("--language", type=str, default="en", help="Language code (default: en)")
    parser.add_argument("--country", type=str, default="US", help="Country code (default: US)")
    parser.add_argument("--rating", type=str, default="Any rating", help="Rating filter (default: Any rating)")
    parser.add_argument("--collect-contact", action="store_true", help="Collect contact information from websites")
    parser.add_argument("--output", type=str, help="Output filename (default: timestamped filename)")
    parser.add_argument("--output-dir", type=str, default="results", help="Output directory (default: results)")
    
    return parser.parse_args()

def main():
    """Main function"""
    # Setup environment
    system = setup_environment()
    
    # Parse arguments
    args = parse_arguments()
    
    # Import backend
    try:
        from backend import Backend
        logger.info("Successfully imported backend module")
    except ImportError as e:
        logger.error(f"Failed to import backend module: {str(e)}")
        logger.error("Please make sure you have installed all dependencies:")
        logger.error("  pip install -r requirements.txt")
        logger.error(f"  pip install -r requirements-{system}.txt")
        sys.exit(1)
    
    # Run scraper
    try:
        logger.info("Initializing Google Maps Scraper")
        backend = Backend(
            language=args.language,
            country=args.country,
            default_rating=args.rating,
            collect_contact=args.collect_contact
        )
        
        if not args.url:
            logger.error("No URL provided. Please specify a Google Maps URL with --url")
            sys.exit(1)
        
        logger.info(f"Scraping URL: {args.url}")
        backend.go_results(args.url)
        
        total_pages = backend.module.get_total_pages()
        total_results = backend.module.get_total_results()
        logger.info(f"Found {total_results} results across {total_pages} pages")
        
        # Collect results
        all_results = []
        for result in backend.iter_results():
            all_results.append(result)
            logger.info(f"Processed: {result.name}")
        
        # Save results
        if all_results:
            csv_path = backend.save_to_csv(
                all_results,
                filename=args.output,
                directory=args.output_dir
            )
            logger.info(f"Results saved to: {csv_path}")
        else:
            logger.warning("No results found to save")
        
    except Exception as e:
        logger.error(f"Error running scraper: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main() 