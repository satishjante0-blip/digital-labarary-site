"""
Book PDF Generation Service
Generates standard PDF documents for reading and downloading books
without requiring external network access or 3rd-party dependencies.
"""
import re

def clean_pdf_text(text):
    if not text:
        return ""
    return str(text).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

def generate_book_pdf(book):
    title = clean_pdf_text(book.title)
    author = clean_pdf_text(book.author)
    category = clean_pdf_text(book.category)
    isbn = clean_pdf_text(book.isbn)
    pub_year = str(book.publication_year or 2024)
    sem = str(book.semester or 1)

    content_lines = [
        "BT",
        "/F1 18 Tf",
        "50 730 Td",
        f"({title}) Tj",
        "/F1 12 Tf",
        "0 -28 Td",
        f"(Author: {author}) Tj",
        "0 -20 Td",
        f"(Department: {category} | Semester: Semester {sem}) Tj",
        "0 -20 Td",
        f"(ISBN: {isbn} | Edition Year: {pub_year}) Tj",
        "0 -30 Td",
        "(========================================================================) Tj",
        "/F1 13 Tf",
        "0 -25 Td",
        "(GURU NANAK INSTITUTE OF TECHNOLOGY - CENTRAL DIGITAL LIBRARY) Tj",
        "/F1 11 Tf",
        "0 -20 Td",
        "(Official Academic E-Book Edition - Approved for Student Coursework) Tj",
        "0 -25 Td",
        "(------------------------------------------------------------------------) Tj",
        "/F1 12 Tf",
        "0 -25 Td",
        "(COURSE SYLLABUS & MODULE BLUEPRINT:) Tj",
        "/F1 10 Tf",
        "0 -22 Td",
        "(Module 1: Fundamental Principles, Mathematical Formulations & Foundations) Tj",
        "0 -18 Td",
        "(Module 2: Core Engineering Architecture, Design Patterns & Applied Concepts) Tj",
        "0 -18 Td",
        "(Module 3: Experimental Analysis, Performance Metrics & Laboratory Practicals) Tj",
        "0 -18 Td",
        "(Module 4: Advanced Industry Applications, Emerging Paradigms & Case Studies) Tj",
        "0 -18 Td",
        "(Module 5: Semester Examination Comprehensive Review, Solved Numerical & FAQs) Tj",
        "0 -28 Td",
        "(------------------------------------------------------------------------) Tj",
        "/F1 11 Tf",
        "0 -22 Td",
        "(STUDY NOTES & REFERENCE GUIDANCE:) Tj",
        "/F1 9 Tf",
        "0 -18 Td",
        "(1. Review each chapter unit alongside your designated semester syllabus.) Tj",
        "0 -16 Td",
        "(2. Complete the end-of-module assessment questions before university examinations.) Tj",
        "0 -16 Td",
        "(3. Digital copies are issued under institutional fair-use academic licensing.) Tj",
        "0 -35 Td",
        "(Digital Knowledge & Circulation Portal - Guru Nanak Institute of Technology) Tj",
        "ET"
    ]

    stream_content = "\n".join(content_lines)
    stream_bytes = stream_content.encode('latin1', errors='replace')
    stream_len = len(stream_bytes)

    header = b"%PDF-1.4\n"
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = (
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        b"endobj\n"
    )
    obj4 = (
        f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode('latin1')
        + stream_bytes
        + b"\nendstream\nendobj\n"
    )
    obj5 = b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"

    pos0 = 0
    pos1 = len(header)
    pos2 = pos1 + len(obj1)
    pos3 = pos2 + len(obj2)
    pos4 = pos3 + len(obj3)
    pos5 = pos4 + len(obj4)
    xref_pos = pos5 + len(obj5)

    xref = (
        f"xref\n0 6\n"
        f"0000000000 65535 f \n"
        f"{pos1:010d} 00000 n \n"
        f"{pos2:010d} 00000 n \n"
        f"{pos3:010d} 00000 n \n"
        f"{pos4:010d} 00000 n \n"
        f"{pos5:010d} 00000 n \n"
        f"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode('latin1')

    return header + obj1 + obj2 + obj3 + obj4 + obj5 + xref
