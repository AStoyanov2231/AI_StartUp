#!/usr/bin/env python3

import sys
import re
from pathlib import Path
from typing import List, Dict, Any

from google import genai
from pypdf import PdfReader

from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    ListFlowable,
    ListItem
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from PDF."""
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


def analyze_pdf_structure(text: str) -> Dict[str, Any]:
    """Analyze the structure of the PDF text and return structural information."""
    structure = {
        "headings": [],
        "numbered_lists": [],
        "paragraphs": [],
        "total_elements": 0,
        "structure_map": []
    }
    
    # Split by both double newlines and single newlines to catch more structure
    lines = text.split('\n')
    paragraphs = []
    current_para = []
    
    # Group lines into paragraphs
    for line in lines:
        line = line.strip()
        if not line:
            if current_para:
                paragraphs.append('\n'.join(current_para))
                current_para = []
        else:
            current_para.append(line)
    
    # Add the last paragraph if it exists
    if current_para:
        paragraphs.append('\n'.join(current_para))
    
    element_counter = 0
    current_list_items = []
    
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
            
        element_counter += 1
        
        # Check for main headings (# Title)
        if para.startswith("# "):
            heading_text = para[2:].strip()
            structure["headings"].append({
                "level": 1,
                "text": heading_text,
                "position": element_counter,
                "paragraph_index": i
            })
            structure["structure_map"].append({
                "type": "heading1",
                "content": heading_text,
                "position": element_counter
            })
            
        # Check for section headings (## Subtitle)
        elif para.startswith("## "):
            heading_text = para[3:].strip()
            structure["headings"].append({
                "level": 2,
                "text": heading_text,
                "position": element_counter,
                "paragraph_index": i
            })
            structure["structure_map"].append({
                "type": "heading2",
                "content": heading_text,
                "position": element_counter
            })
            
        # Check for potential headings (all caps, short lines)
        elif (len(para) < 100 and para.isupper() and 
              not re.match(r"^\d+\.", para) and 
              len(para.split()) <= 10):
            structure["headings"].append({
                "level": 3,
                "text": para,
                "position": element_counter,
                "paragraph_index": i
            })
            structure["structure_map"].append({
                "type": "heading3",
                "content": para,
                "position": element_counter
            })
            
        # Check for numbered list items (various formats)
        elif re.match(r"^\d+\.\s", para):
            list_number = re.match(r"^(\d+)\.", para).group(1)
            item_text = re.sub(r"^\d+\.\s+", "", para)
            
            list_item = {
                "number": int(list_number),
                "text": item_text,
                "position": element_counter,
                "paragraph_index": i
            }
            
            current_list_items.append(list_item)
            structure["structure_map"].append({
                "type": "list_item",
                "content": item_text,
                "number": int(list_number),
                "position": element_counter
            })
            
        # Check for multi-line paragraphs that might contain numbered items
        elif '\n' in para and any(re.match(r"^\d+\.", line.strip()) for line in para.split('\n')):
            # Split the paragraph into individual numbered items
            lines_in_para = para.split('\n')
            for line in lines_in_para:
                line = line.strip()
                if re.match(r"^\d+\.\s", line):
                    element_counter += 1
                    list_number = re.match(r"^(\d+)\.", line).group(1)
                    item_text = re.sub(r"^\d+\.\s+", "", line)
                    
                    list_item = {
                        "number": int(list_number),
                        "text": item_text,
                        "position": element_counter,
                        "paragraph_index": i
                    }
                    
                    current_list_items.append(list_item)
                    structure["structure_map"].append({
                        "type": "list_item",
                        "content": item_text,
                        "number": int(list_number),
                        "position": element_counter
                    })
            element_counter -= 1  # Adjust since we incremented inside the loop
            
        # Regular paragraph
        else:
            # If we were building a list and now hit a regular paragraph, save the list
            if current_list_items:
                structure["numbered_lists"].append({
                    "items": current_list_items.copy(),
                    "start_position": current_list_items[0]["position"],
                    "end_position": current_list_items[-1]["position"]
                })
                current_list_items = []
            
            structure["paragraphs"].append({
                "text": para,
                "position": element_counter,
                "paragraph_index": i,
                "has_bold": "**" in para
            })
            structure["structure_map"].append({
                "type": "paragraph",
                "content": para[:100] + "..." if len(para) > 100 else para,
                "position": element_counter
            })
    
    # Handle any remaining list items
    if current_list_items:
        structure["numbered_lists"].append({
            "items": current_list_items.copy(),
            "start_position": current_list_items[0]["position"],
            "end_position": current_list_items[-1]["position"]
        })
    
    structure["total_elements"] = element_counter
    return structure


def format_structure_for_llm(structure: Dict[str, Any]) -> str:
    """Format the structure information for the LLM prompt."""
    structure_info = "**DOCUMENT STRUCTURE ANALYSIS:**\n\n"
    
    # Overall structure summary
    structure_info += f"Total document elements: {structure['total_elements']}\n"
    structure_info += f"Headings found: {len(structure['headings'])}\n"
    structure_info += f"Numbered lists found: {len(structure['numbered_lists'])}\n"
    structure_info += f"Regular paragraphs: {len(structure['paragraphs'])}\n\n"
    
    # Document structure map
    structure_info += "**DOCUMENT STRUCTURE MAP:**\n"
    for item in structure["structure_map"]:
        if item["type"] == "heading1":
            structure_info += f"{item['position']}. MAIN HEADING: {item['content']}\n"
        elif item["type"] == "heading2":
            structure_info += f"{item['position']}. SECTION HEADING: {item['content']}\n"
        elif item["type"] == "heading3":
            structure_info += f"{item['position']}. TITLE/HEADING: {item['content']}\n"
        elif item["type"] == "list_item":
            structure_info += f"{item['position']}. LIST ITEM {item['number']}: {item['content'][:50]}...\n"
        elif item["type"] == "paragraph":
            structure_info += f"{item['position']}. PARAGRAPH: {item['content'][:50]}...\n"
    
    structure_info += "\n"
    
    # Detailed headings information
    if structure["headings"]:
        structure_info += "**HEADINGS DETAILS:**\n"
        for heading in structure["headings"]:
            if heading["level"] == 1:
                level_name = "MAIN"
            elif heading["level"] == 2:
                level_name = "SECTION"
            else:
                level_name = "TITLE"
            structure_info += f"- Position {heading['position']}: {level_name} HEADING - \"{heading['text']}\"\n"
        structure_info += "\n"
    
    # Detailed numbered lists information
    if structure["numbered_lists"]:
        structure_info += "**NUMBERED LISTS DETAILS:**\n"
        for i, num_list in enumerate(structure["numbered_lists"], 1):
            structure_info += f"List {i} (positions {num_list['start_position']}-{num_list['end_position']}):\n"
            for item in num_list["items"]:
                structure_info += f"  {item['number']}. {item['text'][:60]}...\n"
            structure_info += "\n"
    
    return structure_info


def load_prompt_template() -> str:
    """Load the prompt template from file."""
    template_path = Path("gemini_prompt_template.txt")
    if template_path.exists():
        return template_path.read_text(encoding='utf-8')
    else:
        # Fallback basic template if file doesn't exist
        return """You are a professional text processing assistant. The user has provided the following request:
"{user_request}"

Please process the following text according to the user's request:

{structure_info}

Original text:
{text}

Please provide only the processed and formatted text as your response."""


def process_with_llm(text: str, request: str, structure: Dict[str, Any]) -> str:
    """Send text to Gemini LLM with structure information and get response."""
    api_key = "AIzaSyAMtV5ZWs1DJmG8rcEDXRxdep1HW3enOhI"
    client = genai.Client(api_key=api_key)

    # Load the prompt template
    template = load_prompt_template()
    
    # Format structure information for LLM
    structure_info = format_structure_for_llm(structure)
    
    # Create the full prompt using the template
    prompt = template.format(
        user_request=request,
        structure_info=structure_info,
        text=text
    )

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )

    return response.text.strip()


def set_pdf_styles():
    """Return customized styles for headings, normal text, and lists."""
    styles = getSampleStyleSheet()

    heading1 = ParagraphStyle(
        'Heading1',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceBefore=12,
        spaceAfter=12
    )

    heading2 = ParagraphStyle(
        'Heading2',
        parent=styles['Heading2'],
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        spaceBefore=10,
        spaceAfter=10
    )

    normal = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=12,
        leading=16,
        alignment=TA_JUSTIFY,
        spaceBefore=6,
        spaceAfter=6
    )

    bullet = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontSize=12,
        leading=16,
        leftIndent=20,
        firstLineIndent=-10,
        spaceBefore=2,
        spaceAfter=2
    )

    return heading1, heading2, normal, bullet


def create_pdf(text: str, output_path: str):
    """Create a well-formatted PDF with headings, paragraphs, and lists."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch
    )

    heading1, heading2, normal, bullet = set_pdf_styles()

    story = []
    paragraphs = text.split('\n\n')

    list_items = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # HEADINGS
        if para.startswith("## "):
            story.append(Paragraph(para[3:], heading2))
        elif para.startswith("# "):
            story.append(Paragraph(para[2:], heading1))
        # LIST ITEM (numbered)
        elif re.match(r"^\d+\.\s", para):
            item_text = re.sub(r"^\d+\.\s+", "", para)
            item_text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', item_text)
            list_items.append(ListItem(Paragraph(item_text, bullet)))
        # REGULAR PARAGRAPH
        else:
            para = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', para)
            if list_items:
                story.append(ListFlowable(list_items, bulletType='1'))
                list_items = []
            story.append(Paragraph(para, normal))

    # Add any remaining list at the end
    if list_items:
        story.append(ListFlowable(list_items, bulletType='1'))

    doc.build(story)


def main():
    """Main function."""
    if len(sys.argv) != 4:
        print("Usage: python modify_pdf.py input.pdf output.pdf 'request'")
        sys.exit(1)

    input_pdf = sys.argv[1]
    output_pdf = sys.argv[2]
    request = sys.argv[3]

    if not Path(input_pdf).exists():
        print(f"Error: {input_pdf} not found")
        sys.exit(1)

    # Extract text from PDF
    text = extract_pdf_text(input_pdf)

    # Analyze PDF structure
    structure = analyze_pdf_structure(text)

    # Process with LLM
    processed_text = process_with_llm(text, request, structure)

    # Create new PDF
    create_pdf(processed_text, output_pdf)

    print(f"Done! Output saved to {output_pdf}")


def debug_structure(input_pdf: str):
    """Debug function to print detailed structure analysis."""
    if not Path(input_pdf).exists():
        print(f"Error: {input_pdf} not found")
        return
    
    text = extract_pdf_text(input_pdf)
    structure = analyze_pdf_structure(text)
    structure_info = format_structure_for_llm(structure)
    
    print("=== DETAILED STRUCTURE ANALYSIS ===")
    print(structure_info)
    print("=" * 50)


if __name__ == "__main__":
    main()