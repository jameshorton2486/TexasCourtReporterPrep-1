#!/usr/bin/env python3
import logging
from utils.text_to_pdf import convert_text_to_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Convert study materials to PDF format."""
    input_file = "study_materials.txt"
    output_dir = "pdf_files"
    
    try:
        output_file = convert_text_to_pdf(input_file, output_dir)
        if output_file:
            logger.info(f"Successfully converted {input_file} to {output_file}")
        else:
            logger.error(f"Failed to convert {input_file} to PDF")
    except Exception as e:
        logger.error(f"Error converting study materials: {str(e)}")

if __name__ == "__main__":
    main()