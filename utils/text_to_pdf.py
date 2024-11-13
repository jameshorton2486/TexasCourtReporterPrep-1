from fpdf import FPDF
import os
import logging

logger = logging.getLogger(__name__)

def convert_text_to_pdf(input_file: str, output_dir: str) -> str:
    """Convert a text file containing questions to PDF format."""
    try:
        # Create PDF object
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        
        # Read text file
        with open(input_file, 'r', encoding='utf-8') as file:
            content = file.read()
            
        # Write content to PDF
        pdf.multi_cell(0, 10, content)
        
        # Generate output filename
        output_file = os.path.join(
            output_dir,
            os.path.splitext(os.path.basename(input_file))[0] + '.pdf'
        )
        
        # Save PDF
        pdf.output(output_file)
        logger.info(f"Successfully converted {input_file} to {output_file}")
        return output_file
        
    except Exception as e:
        logger.error(f"Error converting {input_file} to PDF: {str(e)}")
        return None
