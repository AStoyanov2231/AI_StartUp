from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate
from reportlab.lib.styles import getSampleStyleSheet

# Register your handwriting font
pdfmetrics.registerFont(TTFont('Handwriting', 'fonts/Caveat-Medium.ttf'))

# Create a PDF document
doc = SimpleDocTemplate("handwritten_paragraph.pdf", pagesize=letter)

# Use a style and override it to use your font and smaller size
styles = getSampleStyleSheet()
handwriting_style = styles['Normal'].clone('handwriting')
handwriting_style.fontName = 'Handwriting'
handwriting_style.fontSize = 24  # or smaller, e.g., 12
handwriting_style.leading = 40  # line height; adjust as needed

# Your text
text = """
Как ти се струва този текст?<br/>
Ami toz tekst?<br/>
What do you think of this text?<br/>
Hallo, wie geht es dir?<br/>
Ciao, come stai?
"""

# Create a Paragraph flowable
paragraph = Paragraph(text, style=handwriting_style)

# Build the PDF
doc.build([paragraph])