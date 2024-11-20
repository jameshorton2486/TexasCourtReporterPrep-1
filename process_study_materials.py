#!/usr/bin/env python3
import os
import logging
import magic
from pathlib import Path
from utils.text_to_pdf import convert_text_to_pdf
import time
from typing import Optional, Tuple, List
import traceback
import shutil
import hashlib
from datetime import datetime

# Configure logging with JSON format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PDFValidationError(Exception):
    """Custom exception for PDF validation errors."""
    pass

def calculate_file_hash(file_path: str) -> str:
    """Calculate SHA-256 hash of a file for integrity checking."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def validate_pdf(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Enhanced PDF file validation with detailed checks.
    Returns: (is_valid, error_message)
    """
    try:
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
            
        # Check file size (20MB limit)
        max_size = 20 * 1024 * 1024  # 20MB
        file_size = os.path.getsize(file_path)
        if file_size > max_size:
            return False, f"File too large: {file_path} exceeds 20MB limit (size: {file_size/1024/1024:.2f}MB)"
            
        if file_size == 0:
            return False, f"File is empty: {file_path}"
            
        # Validate file type using python-magic
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(file_path)
        
        valid_types = {'application/pdf', 'application/x-pdf'}
        if file_type not in valid_types:
            return False, f"Invalid file type: {file_type}, expected PDF"
            
        # Check file extension
        if not file_path.lower().endswith('.pdf'):
            return False, f"Invalid file extension: {file_path}, expected .pdf"
            
        # Calculate and log file hash for integrity checking
        file_hash = calculate_file_hash(file_path)
        logger.info(f"File hash for {file_path}: {file_hash}")
            
        return True, None
        
    except Exception as e:
        error_msg = f"Validation error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

def create_backup(file_path: str, backup_dir: str) -> Tuple[bool, Optional[str]]:
    """
    Create a backup of a file with timestamp and hash verification.
    Returns: (success, backup_path or error_message)
    """
    try:
        if not os.path.exists(file_path):
            return False, f"Source file not found: {file_path}"
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = os.path.basename(file_path)
        backup_name = f"{os.path.splitext(file_name)[0]}_backup_{timestamp}.pdf"
        backup_path = os.path.join(backup_dir, backup_name)
        
        # Create backup directory if it doesn't exist
        os.makedirs(backup_dir, exist_ok=True)
        
        # Calculate source file hash
        source_hash = calculate_file_hash(file_path)
        
        # Create backup
        shutil.copy2(file_path, backup_path)
        
        # Verify backup integrity
        backup_hash = calculate_file_hash(backup_path)
        if source_hash != backup_hash:
            os.remove(backup_path)
            return False, "Backup verification failed: hash mismatch"
            
        logger.info(f"Created verified backup: {backup_path}")
        return True, backup_path
        
    except Exception as e:
        error_msg = f"Backup error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

def setup_directories() -> Tuple[bool, List[str]]:
    """
    Create necessary directories if they don't exist.
    Returns: (success, list of created/verified directories)
    """
    try:
        dirs = ["pdf_files", "processed_questions", "backup"]
        created_dirs = []
        
        for dir_name in dirs:
            try:
                os.makedirs(dir_name, exist_ok=True)
                created_dirs.append(dir_name)
                logger.info(f"Directory created/verified: {dir_name}")
            except Exception as e:
                logger.error(f"Error creating directory {dir_name}: {str(e)}")
                return False, created_dirs
                
        return True, created_dirs
        
    except Exception as e:
        logger.error(f"Error in directory setup: {str(e)}", exc_info=True)
        return False, []

def process_study_materials() -> bool:
    """Enhanced study materials processing with improved error handling and validation."""
    input_file = "study_materials.txt"
    output_dir = "pdf_files"
    
    try:
        # Initial validation
        if not os.path.exists(input_file):
            logger.error(f"Input file not found: {input_file}")
            return False
            
        # Check if file is empty
        if os.path.getsize(input_file) == 0:
            logger.error(f"Input file is empty: {input_file}")
            return False
            
        # Setup directories with enhanced error handling
        setup_success, created_dirs = setup_directories()
        if not setup_success:
            logger.error("Failed to setup required directories")
            return False
            
        # Create backup of existing file if it exists
        output_file = os.path.join(output_dir, "study_materials.pdf")
        if os.path.exists(output_file):
            backup_success, backup_result = create_backup(output_file, "backup")
            if not backup_success:
                logger.error(f"Backup failed: {backup_result}")
                return False
                
        # Convert to PDF with enhanced error handling
        try:
            start_time = time.time()
            logger.info(f"Converting {input_file} to PDF...")
            
            result = convert_text_to_pdf(input_file, output_dir)
            if not result:
                logger.error(f"Failed to convert {input_file} to PDF")
                return False
                
            processing_time = time.time() - start_time
            logger.info(f"PDF conversion completed in {processing_time:.2f} seconds")
                
            # Validate generated PDF
            is_valid, error_msg = validate_pdf(output_file)
            if not is_valid:
                logger.error(f"Generated PDF validation failed: {error_msg}")
                return False
                
            logger.info(f"Successfully converted {input_file} to PDF: {result}")
            
            # Create a backup of the newly generated PDF
            backup_success, backup_result = create_backup(result, "backup")
            if not backup_success:
                logger.warning(f"Failed to create backup of new PDF: {backup_result}")
                
            return True
            
        except Exception as e:
            logger.error(f"Error during PDF conversion: {str(e)}", exc_info=True)
            return False
            
    except Exception as e:
        logger.error(f"Error processing study materials: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    try:
        logger.info("Starting study materials processing...")
        if process_study_materials():
            logger.info("Study materials processing completed successfully")
        else:
            logger.error("Study materials processing failed")
    except Exception as e:
        logger.error(f"Unexpected error in main: {str(e)}", exc_info=True)
        traceback.print_exc()
