from fpdf import FPDF
import os
import logging
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

class PDFFormatError(Exception):
    """Custom exception for PDF formatting errors."""
    pass

class TextToPDFConverter:
    """Handles conversion of text files to PDF with enhanced formatting."""
    
    def __init__(self, margin: float = 20, font_size: float = 12):
        self.margin = margin
        self.font_size = font_size
        self.errors: List[str] = []

    def validate_text_file(self, file_path: str) -> bool:
        """Validate text file existence and content."""
        try:
            path = Path(file_path)
            if not path.exists():
                self.errors.append(f"File not found: {file_path}")
                return False
                
            if not path.is_file():
                self.errors.append(f"Not a file: {file_path}")
                return False
                
            if path.stat().st_size == 0:
                self.errors.append(f"Empty file: {file_path}")
                return False
                
            # Check if file is readable and contains text
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read(1024)  # Read first 1KB to check content
                if not content.strip():
                    self.errors.append(f"File contains no text content: {file_path}")
                    return False
                    
            return True
            
        except UnicodeDecodeError:
            self.errors.append(f"File is not a valid text file: {file_path}")
            return False
        except Exception as e:
            self.errors.append(f"Error validating file {file_path}: {str(e)}")
            return False

    def format_text_content(self, content: str) -> List[str]:
        """Format text content for PDF conversion."""
        try:
            # Split content into sections
            sections = []
            current_section = []
            
            for line in content.split('\n'):
                line = line.strip()
                if line:
                    current_section.append(line)
                elif current_section:
                    sections.append('\n'.join(current_section))
                    current_section = []
                    
            if current_section:
                sections.append('\n'.join(current_section))
                
            return sections
            
        except Exception as e:
            raise PDFFormatError(f"Error formatting content: {str(e)}")

    def create_pdf(self, sections: List[str], output_file: str) -> bool:
        """Create PDF with formatted sections."""
        try:
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=self.margin)
            pdf.add_page()
            pdf.set_font("Arial", size=self.font_size)
            
            # Add content with proper formatting
            for section in sections:
                if section.strip():
                    # Add section title if it looks like one
                    if section.isupper() or section.endswith(':'):
                        pdf.set_font("Arial", 'B', self.font_size + 2)
                        pdf.multi_cell(0, 10, section, align='L')
                        pdf.set_font("Arial", size=self.font_size)
                    else:
                        # Handle question-answer format
                        if '?' in section:
                            parts = section.split('?', 1)
                            question = parts[0] + '?'
                            answers = parts[1] if len(parts) > 1 else ''
                            
                            pdf.multi_cell(0, 10, question, align='L')
                            if answers:
                                pdf.set_x(pdf.get_x() + 10)  # Indent answers
                                pdf.multi_cell(0, 8, answers.strip(), align='L')
                        else:
                            pdf.multi_cell(0, 10, section, align='L')
                    
                    pdf.ln(5)  # Add space between sections
                    
            # Save PDF
            pdf.output(output_file)
            return True
            
        except Exception as e:
            raise PDFFormatError(f"Error creating PDF: {str(e)}")

def convert_text_to_pdf(input_file: str, output_dir: str) -> Optional[str]:
    """Convert a text file containing questions to PDF format with enhanced handling."""
    converter = TextToPDFConverter()
    logger.info(f"Starting conversion of {input_file} to PDF")
    
    try:
        # Validate input file
        if not converter.validate_text_file(input_file):
            for error in converter.errors:
                logger.error(error)
            return None
            
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate output filename
        output_file = os.path.join(
            output_dir,
            os.path.splitext(os.path.basename(input_file))[0] + '.pdf'
        )
        
        # Read and format content
        with open(input_file, 'r', encoding='utf-8') as file:
            content = file.read()
        sections = converter.format_text_content(content)
        
        # Create PDF
        if converter.create_pdf(sections, output_file):
            logger.info(f"Successfully converted {input_file} to {output_file}")
            return output_file
            
        return None
        
    except PDFFormatError as e:
        logger.error(f"PDF formatting error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error converting {input_file} to PDF: {str(e)}")
        return None
