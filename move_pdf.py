import os

def move_pdf():
    # Create pdf_files directory if it doesn't exist
    os.makedirs('pdf_files', exist_ok=True)
    
    # Source and destination paths
    source = "More questions part 2.pdf"
    destination = os.path.join("pdf_files", source)
    
    try:
        # Read source file
        with open(source, 'rb') as src_file:
            content = src_file.read()
            
        # Write to destination
        with open(destination, 'wb') as dst_file:
            dst_file.write(content)
            
        # Remove source file after successful copy
        os.remove(source)
        return True
    except Exception as e:
        print(f"Error moving file: {str(e)}")
        return False

if __name__ == "__main__":
    move_pdf()
