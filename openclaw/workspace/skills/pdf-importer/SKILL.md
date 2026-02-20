---
name: pdf-importer
description: "Imports leads from PDF files into the database. Use when the owner sends PDF files containing client lists, contact sheets, or lead data. Extracts names, phone numbers, emails, and addresses using pdfplumber."
tools:
  - Bash
  - Read
---

# PDF Importer - Extract Leads from PDF Files

Import existing contacts from PDF files into the Empire Sales Agent database.

## How to use

### Import a single PDF:
```bash
cd ~/empire-sales-agent && source venv/bin/activate && python database/seed_from_pdf.py /path/to/file.pdf
```

### Import all PDFs in a directory:
```bash
cd ~/empire-sales-agent && source venv/bin/activate && python database/seed_from_pdf.py /path/to/pdfs/
```

## When the owner sends a PDF via WhatsApp

1. Save the file to `~/empire-sales-agent/data/pdfs/`
2. Run the importer on the saved file
3. Report the results back to the owner:
   - How many leads were found
   - How many were successfully imported
   - How many were duplicates (skipped)

## What the importer extracts

The script uses two strategies:

1. **Table extraction**: If the PDF has structured tables, it identifies columns (name, phone, email, address) and extracts row by row
2. **Text extraction**: If unstructured, it uses regex to find phone numbers, then looks for nearby names and emails

## Supported formats

- Client contact lists
- Estimate records
- Phone number lists
- Any PDF with names and phone numbers

## Data quality

- Phone numbers are normalized to +1XXXXXXXXXX format
- Duplicate phones are automatically skipped
- Leads from PDFs get source = 'pdf' and base score = 25-30
- Cities are auto-detected for Lee/Collier county assignment

## Troubleshooting

If extraction quality is low:
- Try opening the PDF and checking if it's text-based or image-based
- Image-based PDFs (scanned documents) need OCR — not currently supported
- Suggest the owner provide data in CSV or Excel format instead
