import os
import logging
import shutil
from pathlib import Path
import magic
from typing import List, Tuple

logger = logging.getLogger(__name__)

class PDFMover:
    """Handles PDF file movement with validation and error handling."""
    
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit
    ALLOWED_MIME_TYPES = {'application/pdf'}
    
    def __init__(self, destination_dir: str = 'pdf_files'):
        """Initialize with destination directory."""
        self.destination_dir = Path(destination_dir)
        self.errors: List[str] = []
        
    def setup_directory(self) -> bool:
        """Create destination directory if it doesn't exist."""
        try:
            self.destination_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Destination directory setup successful: {self.destination_dir}")
            return True
        except Exception as e:
            error_msg = f"Failed to create destination directory: {str(e)}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
            
    def validate_file(self, file_path: Path) -> bool:
        """Validate PDF file size and type."""
        try:
            if not file_path.exists():
                error_msg = f"File not found: {file_path}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                return False
                
            # Check file size
            file_size = file_path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                error_msg = f"File exceeds size limit of {self.MAX_FILE_SIZE/1024/1024}MB: {file_path}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                return False
                
            # Check file type using python-magic
            mime_type = magic.from_file(str(file_path), mime=True)
            if mime_type not in self.ALLOWED_MIME_TYPES:
                error_msg = f"Invalid file type {mime_type} for file: {file_path}"
                logger.error(error_msg)
                self.errors.append(error_msg)
                return False
                
            logger.info(f"File validation successful: {file_path}")
            return True
            
        except Exception as e:
            error_msg = f"Error validating file {file_path}: {str(e)}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
            
    def move_file(self, source_path: Path) -> bool:
        """Move a single PDF file to the destination directory."""
        try:
            if not self.validate_file(source_path):
                return False
                
            destination_path = self.destination_dir / source_path.name
            
            # Check if file already exists in destination
            if destination_path.exists():
                logger.warning(f"File already exists in destination: {destination_path}")
                # Create backup of existing file
                backup_path = destination_path.with_suffix(f".bak{destination_path.suffix}")
                shutil.move(str(destination_path), str(backup_path))
                logger.info(f"Created backup of existing file: {backup_path}")
                
            # Move file to destination
            shutil.move(str(source_path), str(destination_path))
            logger.info(f"Successfully moved file to: {destination_path}")
            return True
            
        except Exception as e:
            error_msg = f"Error moving file {source_path}: {str(e)}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return False
            
    def process_directory(self, source_dir: str = '.') -> Tuple[int, List[str]]:
        """Process all PDF files in the source directory."""
        if not self.setup_directory():
            return 0, self.errors
            
        source_path = Path(source_dir)
        moved_count = 0
        
        try:
            pdf_files = list(source_path.glob('*.pdf'))
            if not pdf_files:
                logger.info("No PDF files found in source directory")
                return 0, self.errors
                
            logger.info(f"Found {len(pdf_files)} PDF files to process")
            
            for pdf_file in pdf_files:
                if self.move_file(pdf_file):
                    moved_count += 1
                    
            logger.info(f"Successfully moved {moved_count} out of {len(pdf_files)} files")
            return moved_count, self.errors
            
        except Exception as e:
            error_msg = f"Error processing directory {source_dir}: {str(e)}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return moved_count, self.errors

def move_pdf() -> Tuple[int, List[str]]:
    """Main function to move PDF files."""
    mover = PDFMover()
    return mover.process_directory()

if __name__ == "__main__":
    moved_count, errors = move_pdf()
    if errors:
        print("Errors encountered:")
        for error in errors:
            print(f"- {error}")
    print(f"Successfully moved {moved_count} PDF files")
