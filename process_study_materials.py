#!/usr/bin/env python3
import os
import logging
from pathlib import Path
from utils.text_to_pdf import convert_text_to_pdf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_directories():
    """Create necessary directories if they don't exist."""
    try:
        os.makedirs("pdf_files", exist_ok=True)
        os.makedirs("processed_questions", exist_ok=True)
        logger.info("Directories created successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating directories: {str(e)}")
        return False

def process_study_materials():
    """Convert study materials to PDF format with enhanced error handling."""
    input_file = "study_materials.txt"
    output_dir = "pdf_files"
    
    try:
        # Check if input file exists
        if not os.path.exists(input_file):
            logger.error(f"Input file not found: {input_file}")
            return False
            
        # Check if file is empty
        if os.path.getsize(input_file) == 0:
            logger.error(f"Input file is empty: {input_file}")
            return False
            
        # Setup directories
        if not setup_directories():
            return False
            
        # Create backup of existing file if it exists
        output_file = os.path.join(output_dir, "study_materials.pdf")
        if os.path.exists(output_file):
            backup_path = os.path.join(output_dir, f"study_materials_backup_{int(time.time())}.pdf")
            os.rename(output_file, backup_path)
            logger.info(f"Created backup of existing PDF: {backup_path}")
            
        # Convert to PDF
        result = convert_text_to_pdf(input_file, output_dir)
        if result:
            logger.info(f"Successfully converted {input_file} to {result}")
            return True
        else:
            logger.error(f"Failed to convert {input_file} to PDF")
            return False
            
    except Exception as e:
        logger.error(f"Error processing study materials: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    if process_study_materials():
        logger.info("Study materials processing completed successfully")
    else:
        logger.error("Study materials processing failed")
