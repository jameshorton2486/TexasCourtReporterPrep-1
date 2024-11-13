from flask import Flask
from app import app, db
from process_pdfs import process_pdfs
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    with app.app_context():
        logger.info("Starting PDF processing...")
        total_added, errors = process_pdfs()
        
        logger.info(f"Total questions added: {total_added}")
        if errors:
            logger.warning("Errors encountered during processing:")
            for error in errors:
                logger.warning(f"- {error}")
        
        return total_added, errors

if __name__ == "__main__":
    main()
