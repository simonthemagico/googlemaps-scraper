from monseigneur.mbackend.tools.proxies import proxytools
from monseigneur.mbackend.core.fetcher import Fetcher
from pytz import timezone
from googlemaps_matrix.module.constants import LANGUAGES, SHORT_LANGUAGES, COUNTRIES, ratings as RATINGS
from googlemaps_matrix.module.exceptions import InvalidUrl
import re
import math
import logging
import os
import sys
import csv
from datetime import datetime


class Backend():
    """
    Google Maps Scraper Backend

    This backend allows searching for places on Google Maps and extracting detailed information
    including contact details, images, ratings, and more.

    Features:
    - Search for places on Google Maps using URLs
    - Filter results by rating (2.0+ to 4.5+)
    - Customize language and country settings
    - Extract detailed information (address, phone, website, etc.)
    - Collect contact information from websites (email, social media)
    - Save results to CSV with proper column headers
    - Collect and process images

    Usage Examples:
    ```python
    # Basic usage
    backend = Backend()
    backend.go_results("https://www.google.com/maps/search/restaurants+in+paris")

    # With custom language and country
    backend = Backend(language="en", country="US")

    # With rating filter
    backend = Backend(default_rating="4.0+")

    # With contact collection enabled
    backend = Backend(collect_contact=True)

    # Iterate through results
    for result in backend.iter_results():
        print(f"Name: {result.name}, Rating: {result.score}")

    # Save results to CSV
    results = list(backend.iter_results())
    backend.save_to_csv(results, filename="my_results.csv")
    ```
    """

    APPNAME = "googlemaps_matrix"
    VERSION = "1.0"
    COPYRIGHT = "Copyright(C) 2012-YEAR leadstrooper"
    DESCRIPTION = "Search for places on Google Maps"
    SHORT_DESCRIPTION = "Search for places on Google Maps"

    def __init__(self, *args, **kwargs):
        """
        Initialize the backend with necessary components

        Args:
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments
                - logger: Custom logger instance
                - language: Default language code (default: "fr")
                - country: Default country code (default: "FR")
                - collect_contact: Whether to collect contact info from websites (default: True)
                - default_rating: Default rating filter (default: "Any rating")
        """
        # Setup logger
        self.logger = kwargs.get('logger', logging.getLogger(self.APPNAME))

        # Prevent duplicate logging by checking if handlers are already set up
        if not self.logger.handlers:
            # Check if propagate is set to True and a parent logger has handlers
            parent_has_handlers = False
            parent = self.logger.parent
            while parent:
                if parent.handlers:
                    parent_has_handlers = True
                    break
                parent = parent.parent

            # Only add handler if no parent has handlers
            if not parent_has_handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)

            # Set level regardless of handlers
            self.logger.setLevel(logging.INFO)

        # Explicitly disable propagation to prevent duplicate logs
        self.logger.propagate = False

        self.logger.info(f"Initializing {self.APPNAME} backend v{self.VERSION}")

        # Initialize components
        self.proxies = proxytools()
        self.timezone = timezone('Europe/Paris')

        # Get configuration from kwargs with defaults
        self.default_language = kwargs.get('language', 'fr')
        self.default_country = kwargs.get('country', 'FR')
        self.default_rating = kwargs.get('default_rating', 'Any rating')
        self.collect_contact = kwargs.get('collect_contact', False)
        self.special_message = ''


        # Initialize module path and build backend
        module_path = os.path.join(os.environ.get('HOME', ''), "mdev/googlemaps_scraper/googlemaps_matrix")
        self.logger.info(f"Using module path: {module_path}")

        try:
            self.fetcher = Fetcher(absolute_path=module_path)
            self.module = self.fetcher.build_backend("module", params={}, logger=self.logger)
            self.logger.info("Backend module initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize backend module: {str(e)}")
            raise

    def go_results(self, url, page=1, language=None, country=None, ratings=None):
        """
        Navigate to search results page

        Args:
            url: Google Maps URL to search
            page: Page number to retrieve (default: 1)
            language: Language code to use (default: None, uses instance default)
            country: Country code to use (default: None, uses instance default)
            ratings: Minimum rating filter (default: None, uses instance default)

        Returns:
            Search results page

        """
        # Use provided parameters or fall back to instance defaults
        language = language or self.default_language
        country = country or self.default_country
        ratings = ratings or self.default_rating

        # Validate ratings parameter
        if ratings not in RATINGS:
            self.logger.warning(f"Invalid rating filter: {ratings}. Using default: {self.default_rating}")
            ratings = self.default_rating

        # Normalize language and country
        if language in LANGUAGES:
            language = LANGUAGES[language]
        elif language not in SHORT_LANGUAGES:
            language = 'en'
        country = COUNTRIES.get(country, 'US')

        # Validate URL format
        if not re.match(r'^https?://(www\.)?google\.[a-z.]+/maps/(search|place)/[^/]*(?!http[s]?://).*$', url):
            self.logger.error(f"Invalid URL format: {url}")
            raise InvalidUrl

        # Handle place URLs differently
        if '/place/' in url:
            self.logger.info(f"Processing place URL: {url} with language={language}, ratings={ratings}")
            return self.module.go_results(url, language, page, ratings)

        # Handle search URLs
        url = url.replace(' ', '%20')
        self.logger.info(f"Processing search URL: {url} with language={language}, country={country}, ratings={ratings}")
        return self.module.go_results(url, language, country, page, ratings)

    def fill_details(self, module_session, Result, existing_result_obj, result_obj, module_params, params):
        """
        Fill in detailed information for a result

        Args:
            module_session: Current session
            Result: Result class
            existing_result_obj: Existing result object if any
            result_obj: Result object to fill
            module_params: Module parameters
            params: Additional parameters

        Returns:
            Filled result object
        """
        self.logger.debug(f"Filling details for result: {getattr(result_obj, 'name', 'Unknown')}")
        result_obj = existing_result_obj or result_obj
        return self.module.fill_result_details(result_obj)

    def fill_images(self, module_session, Result, existing_result_obj, result_obj, module_params, params):
        """
        Fill images for a result

        Args:
            module_session: Current session
            Result: Result class
            existing_result_obj: Existing result object if any
            result_obj: Result object to fill
            module_params: Module parameters
            params: Additional parameters

        Returns:
            Result object with images
        """
        # Get details if needed
        if not self.cluster_obj.params.get('details'):
            self.fill_details(module_session, Result, existing_result_obj, result_obj, module_params, params)

        # Skip if no images
        if result_obj.images_count == 0:
            self.logger.debug(f"No images found for result: {getattr(result_obj, 'name', 'Unknown')}")
            return existing_result_obj or result_obj

        result_obj = existing_result_obj or result_obj

        try:
            # Get image ID and prepare collection
            img_id = self.module.get_image_id(result_obj)
            result_obj.images = result_obj.images or []
            cursor = None
            total_pages = min(10, math.ceil(result_obj.images_count / 24))

            self.logger.info(f"Collecting images for {getattr(result_obj, 'name', 'Unknown')}: {result_obj.images_count} images across {total_pages} pages")

            # Collect images from all pages
            for page_num in range(1, total_pages + 1):
                self.logger.debug(f"Collecting images page {page_num}/{total_pages}")
                page_images, cursor = self.module.fill_images(
                    result_obj, cursor, img_id
                )

                # Add new images only
                new_images = [image for image in page_images if image not in result_obj.images]
                result_obj.images.extend(new_images)
                self.logger.debug(f"Added {len(new_images)} new images from page {page_num}")

                if not cursor:
                    self.logger.debug("No more image pages available")
                    break

            self.special_message += f"✨ Collected {len(result_obj.images)} images (*)\n"
            self.logger.info(f"Successfully collected {len(result_obj.images)} images for {getattr(result_obj, 'name', 'Unknown')}")

        except Exception as e:
            self.logger.error(f"Error collecting images: {str(e)}")
            # Return what we have so far even if there was an error

        return result_obj

    def iter_results(self, *args, **kwargs):
        """
        Iterate through search results

        Args:
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments

        Yields:
            Result objects with filled information
        """
        self.logger.info("Starting to iterate through results")

        try:
            for result in self.module.iter_results():
                self.logger.debug(f"Processing result: {getattr(result, 'name', 'Unknown')}")
                self.special_message = ''

                # Collect contact information if website is available
                if self.collect_contact and result.website:
                    self.logger.debug(f"Collecting contact information from website: {result.website}")

                    # Save original phone number
                    result_phone = result.phone

                    # Get contacts from website
                    try:
                        result = self.module.get_contacts(result)
                        result.additional_phone = result.phone
                        result.phone = result_phone

                        # Add special messages for found contact information
                        if result.facebook:
                            word = "Facebook" + ("s" if result.facebook.count(', ') else '')
                            self.special_message += f'✨ {word} found: {result.facebook} (*)\n'

                        if result.instagram:
                            word = "Instagram" + ("s" if result.instagram.count(', ') else '')
                            self.special_message += f'✨ {word} found: {result.instagram} (*)\n'

                        if result.email:
                            word = "Email" + ("s" if result.email.count(', ') else '')
                            self.special_message += f'✨ {word} found: {result.email} (*)\n'

                        self.special_message = self.special_message.strip()

                    except Exception as e:
                        self.logger.warning(f"Error collecting contacts from {result.website}: {str(e)}")

                yield result

        except Exception as e:
            self.logger.error(f"Error iterating through results: {str(e)}")
            raise

    def save_to_csv(self, results, filename=None, directory=None):
        """
        Save search results to a CSV file with proper column names

        Args:
            results: List of result objects to save
            filename: Optional custom filename (default: googlemaps_results_YYYY-MM-DD_HH-MM-SS.csv)
            directory: Optional directory to save the file (default: current directory)

        Returns:
            Path to the saved CSV file
        """
        # Generate default filename if not provided
        if not filename:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"googlemaps_results_{timestamp}.csv"

        # Use current directory if not specified
        if not directory:
            directory = os.getcwd()

        # Create directory if it doesn't exist
        os.makedirs(directory, exist_ok=True)

        # Full path to the CSV file
        filepath = os.path.join(directory, filename)

        # Define columns to include in the CSV
        columns = [
            'name', 'address', 'city', 'zip_code', 'country', 'phone', 'additional_phone',
            'email', 'website', 'facebook', 'instagram', 'category', 'score', 'ratings',
            'opening_hours', 'is_temporarily_closed', 'is_permanently_closed',
            'lat', 'lng', 'url'
        ]

        # Optional columns that might not be present in all results
        optional_columns = [
            'description', 'price', 'menu', 'booking_link', 'popular_times',
            'special_category', 'has_owner', 'about', 'poi'
        ]

        self.logger.info(f"Saving {len(results)} results to CSV: {filepath}")

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, quoting=csv.QUOTE_MINIMAL)

                # Write header row
                header = columns + [col for col in optional_columns if any(hasattr(r, col) for r in results)]
                writer.writerow(header)

                # Write data rows
                for result in results:
                    row = []
                    for column in header:
                        if hasattr(result, column):
                            value = getattr(result, column)
                            # Handle lists and complex objects
                            if isinstance(value, (list, tuple)):
                                value = ', '.join(str(v) for v in value)
                            row.append(value)
                        else:
                            row.append('')
                    writer.writerow(row)

            self.logger.info(f"Successfully saved results to {filepath}")
            return filepath

        except Exception as e:
            self.logger.error(f"Error saving results to CSV: {str(e)}")
            raise


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                   GOOGLE MAPS SCRAPER DEMO                    ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    # Demo configuration
    search_url = "https://www.google.com/maps/search/restaurants/@48.8566,2.3522,13z"

    print("Available Features:")
    print("  • Custom language and country settings")
    print("  • Rating filters: " + ", ".join(RATINGS))
    print("  • Contact information collection")
    print("  • CSV export with customizable filename and location")
    print("  • Detailed information extraction\n")

    # Example 1: Basic Usage
    print("\n╔═══ EXAMPLE 1: Basic Usage ═══╗")
    try:
        backend = Backend()
        print("Initialized backend with default settings:")
        print(f"  • Language: {backend.default_language}")
        print(f"  • Country: {backend.default_country}")
        print(f"  • Rating filter: {backend.default_rating}")
        print(f"  • Contact collection: {backend.collect_contact}")

        print("\nSearching for restaurants in Paris...")
        backend.go_results(search_url, page=1)

        total_pages = backend.module.get_total_pages()
        total_results = backend.module.get_total_results()

        print(f"\nFound {total_results} results across {total_pages} pages")

        # Get first 3 results for demo purposes
        print("\n=== Sample Results ===")
        all_results = []
        count = 0
        for result in backend.iter_results():
            all_results.append(result)
            count += 1

            print(f"\nResult #{count}:")
            print(f"  • Name: {result.name}")
            print(f"  • Address: {result.address}")
            print(f"  • Rating: {result.score} ({result.ratings} reviews)")
            if result.website:
                print(f"  • Website: {result.website}")
            if result.phone:
                print(f"  • Phone: {result.phone}")

            # Only show 20 results for the demo
            if count >= 20:
                break

        # Save results to CSV
        if all_results:
            csv_path = backend.save_to_csv(all_results, filename="basic_results.csv")
            print(f"\nSample results saved to: {csv_path}")
    except Exception as e:
        logging.error(f"Error in Example 1: {str(e)}")

    # Example 2: Advanced Configuration
    print("\n\n╔═══ EXAMPLE 2: Advanced Configuration ═══╗")
    try:
        # Create backend with custom settings
        backend = Backend(
            language="en",
            country="US",
            default_rating="4.0+",
            collect_contact=True
        )

        print("Initialized backend with custom settings:")
        print(f"  • Language: {backend.default_language} (English)")
        print(f"  • Country: {backend.default_country} (United States)")
        print(f"  • Rating filter: {backend.default_rating}")
        print(f"  • Contact collection: {backend.collect_contact}")

        print("\nSearching for high-rated restaurants...")
        backend.go_results(search_url, page=1)

        total_pages = backend.module.get_total_pages()
        total_results = backend.module.get_total_results()

        print(f"\nFound {total_results} results with 4.0+ rating across {total_pages} pages")

    except Exception as e:
        logging.error(f"Error in Example 2: {str(e)}")

    # Example 3: Parameter Override
    print("\n\n╔═══ EXAMPLE 3: Parameter Override ═══╗")
    try:
        # Create backend with default settings
        backend = Backend()

        print("Initialized backend with default settings")
        print("Overriding parameters for this specific search:")
        print("  • Language: en (English)")
        print("  • Country: DE (Germany)")
        print("  • Rating filter: 3.5+")

        # Override parameters for this specific search
        backend.go_results(
            search_url,
            page=1,
            language="en",
            country="DE",
            ratings="3.5+"
        )

        total_pages = backend.module.get_total_pages()
        total_results = backend.module.get_total_results()

        print(f"\nFound {total_results} results with 3.5+ rating across {total_pages} pages")

    except Exception as e:
        logging.error(f"Error in Example 3: {str(e)}")

    # Example 4: CSV Export Options
    print("\n\n╔═══ EXAMPLE 4: CSV Export Options ═══╗")
    try:
        backend = Backend()
        print("CSV Export Features:")
        print("  • Default filename with timestamp")
        print("  • Custom filename")
        print("  • Custom directory")
        print("  • Automatic column detection")
        print("  • Proper handling of complex data types")

        # Create a sample directory for demonstration
        sample_dir = os.path.join(os.getcwd(), "sample_exports")
        os.makedirs(sample_dir, exist_ok=True)

        # Get a few results for demonstration
        backend.go_results(search_url, page=1)
        all_results = []
        count = 0
        for result in backend.iter_results():
            all_results.append(result)
            count += 1
            if count >= 3:
                break

        if all_results:
            # Example with default filename
            default_path = backend.save_to_csv(all_results)
            print(f"\n1. Default filename: {os.path.basename(default_path)}")

            # Example with custom filename
            custom_filename_path = backend.save_to_csv(all_results, filename="custom_filename.csv")
            print(f"2. Custom filename: {os.path.basename(custom_filename_path)}")

            # Example with custom directory
            custom_dir_path = backend.save_to_csv(all_results, directory=sample_dir)
            print(f"3. Custom directory: {custom_dir_path}")

            # Example with both custom filename and directory
            full_custom_path = backend.save_to_csv(
                all_results,
                filename="full_custom.csv",
                directory=sample_dir
            )
            print(f"4. Custom filename and directory: {full_custom_path}")

            print("\nCSV files include the following columns:")
            print("  • Basic: name, address, phone, website, rating, etc.")
            print("  • Contact: email, facebook, instagram (if collected)")
            print("  • Location: latitude, longitude")
            print("  • Status: opening hours, temporary/permanent closure")
            print("  • Additional: any other available attributes")
    except Exception as e:
        logging.error(f"Error in Example 4: {str(e)}")

    print("\n\n╔═══════════════════════════════════════════════════════════════╗")
    print("║                     END OF DEMONSTRATION                      ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
