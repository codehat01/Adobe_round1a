#!/usr/bin/env python3
import json
import re
import fitz  # PyMuPDF
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict, Counter
import statistics


class PDFOutlineExtractor:
    def __init__(self, pdf_path: str):
        """Initialize extractor"""
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.all_text_blocks = []
        self.font_analysis = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'doc') and self.doc:
            self.doc.close()

    

    def extract_text_blocks(self) -> List[Dict]:
        """Extract text blocks with formatting"""
        text_blocks = []
        
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            blocks = page.get_text("dict")
            
            for block in blocks["blocks"]:
                if "lines" not in block:
                    continue
                    
                for line in block["lines"]:
                    line_text = ""
                    line_spans = []
                    
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if text:
                            line_text += text + " "
                            line_spans.append(span)
                    
                    line_text = line_text.strip()
                    if not line_text or len(line_text) < 2:
                        continue
                    
                    # Use the dominant span for formatting
                    if line_spans:
                        dominant_span = max(line_spans, key=lambda s: len(s["text"]))
                        
                        text_block = {
                            "text": line_text,
                            "font_size": dominant_span["size"],
                            "font_flags": dominant_span["flags"],
                            "font_name": dominant_span.get("font", ""),
                            "x_position": dominant_span["bbox"][0],
                            "y_position": dominant_span["bbox"][1],
                            "page": page_num + 1,
                            "is_bold": bool(dominant_span["flags"] & 2**4),
                            "bbox": dominant_span["bbox"],
                            "line_height": line["bbox"][3] - line["bbox"][1]
                        }
                        
                        text_blocks.append(text_block)
        
        return text_blocks

    def analyze_fonts(self, text_blocks: List[Dict]) -> Dict:
        """Analyze fonts for heading detection"""
        font_sizes = [block["font_size"] for block in text_blocks]
        font_names = [block["font_name"] for block in text_blocks]
        
        # Calculate statistics
        font_counter = Counter(font_sizes)
        name_counter = Counter(font_names)
        
        # Determine body text characteristics
        body_font_size = font_counter.most_common(1)[0][0]
        body_font_name = name_counter.most_common(1)[0][0]
        
        # Calculate percentiles
        sorted_sizes = sorted(font_sizes)
        percentiles = {
            50: sorted_sizes[int(0.50 * len(sorted_sizes))],
            75: sorted_sizes[int(0.75 * len(sorted_sizes))],
            85: sorted_sizes[int(0.85 * len(sorted_sizes))],
            90: sorted_sizes[int(0.90 * len(sorted_sizes))],
            95: sorted_sizes[int(0.95 * len(sorted_sizes))]
        }
        
        return {
            "body_font_size": body_font_size,
            "body_font_name": body_font_name,
            "percentiles": percentiles,
            "size_distribution": font_counter,
            "unique_sizes": len(set(font_sizes)),
            "min_size": min(font_sizes),
            "max_size": max(font_sizes)
        }

    def is_excluded_content(self, text: str, page: int) -> bool:
        """Check if content should be excluded"""
        text_clean = text.strip()
        text_lower = text_clean.lower()
        
        # Length constraints
        if len(text_clean) < 3 or len(text_clean) > 150:
            return True
        
        # Specific exclusion patterns
        exclusion_patterns = [
            # Copyright and legal
            r'copyright|©|all rights reserved|confidential|proprietary',
            # URLs and emails  
            r'http[s]?://|www\.|@[\w\.-]+\.\w+|\.com|\.org|\.net',
            # Dates in various formats (CRITICAL FIX)
            r'^\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}$'
        ]
        
        # Check against patterns
        for pattern in exclusion_patterns:
            if re.match(pattern, text_lower):
                return True
        
        return False

    def detect_heading_patterns(self, text: str) -> Tuple[bool, int, int]:
        """Detect heading patterns. Returns (is_heading, level, confidence)"""
        text_stripped = text.strip()
        confidence = 0
        level = 0
        
        # Pattern 1: Numbered sections with proper hierarchy
        numbered_match = re.match(r'^(\d+)(\.\d+)*\.?\s+(.+)$', text_stripped)
        if numbered_match:
            dots = numbered_match.group(2)
            content = numbered_match.group(3).strip()
            
            # Avoid table data or simple numbers
            if len(content) > 5 and not re.match(r'^\d+$', content):
                level = 1 if not dots else min(dots.count('.') + 1, 3)
                confidence = 90
                return True, level, confidence
        
        # Pattern 2: Letter-based sections (A., B., etc.)  
        letter_match = re.match(r'^([A-Z])(\.\d+)*\.?\s+(.+)$', text_stripped)
        if letter_match:
            content = letter_match.group(3).strip()
            if len(content) > 5:
                level = 1
                confidence = 80
                return True, level, confidence
        
        # Pattern 3: Roman numerals
        roman_match = re.match(r'^([IVX]+)\.?\s+(.+)$', text_stripped)
        if roman_match:
            content = roman_match.group(2).strip()
            if len(content) > 5:
                level = 1
                confidence = 70
                return True, level, confidence
        
        # Pattern 4: Colon endings (but not ratios or times)
        if (text_stripped.endswith(':') and 
            len(text_stripped) > 8 and 
            not re.search(r'\d+:\d+', text_stripped) and
            text_stripped.count(':') == 1):
            confidence = 60
            level = 2  # Usually sub-headings
            return True, level, confidence
        
        # Pattern 5: All caps (selective)
        if (text_stripped.isupper() and 
            10 <= len(text_stripped) <= 60 and
            not re.match(r'^[A-Z\s]+\d+[A-Z\s]*$', text_stripped)):  # Avoid "VERSION 1.0" etc.
            confidence = 50
            level = 1
            return True, level, confidence
            
        return False, 0, 0

    def calculate_heading_likelihood(self, block: Dict, font_analysis: Dict) -> Tuple[bool, str, int]:
        """Calculate if text is a heading. Returns (is_heading, level, confidence)"""
        text = block["text"]
        font_size = block["font_size"]
        is_bold = block["is_bold"]
        font_name = block["font_name"]
        
        # Base exclusion
        if self.is_excluded_content(text, block["page"]):
            return False, None, 0
        
        total_confidence = 0
        suggested_level = 3
        
        # 1. Pattern-based detection (highest priority)
        has_pattern, pattern_level, pattern_confidence = self.detect_heading_patterns(text)
        if has_pattern:
            total_confidence += pattern_confidence
            suggested_level = pattern_level
        
        # 2. Font size analysis
        body_size = font_analysis["body_font_size"]
        size_ratio = font_size / body_size
        
        if size_ratio >= 1.5:  # Significantly larger
            total_confidence += 60
            if size_ratio >= 2.0:
                suggested_level = min(suggested_level, 1)
            elif size_ratio >= 1.8:
                suggested_level = min(suggested_level, 2)
        elif size_ratio >= 1.2:  # Moderately larger
            total_confidence += 30
            suggested_level = min(suggested_level, 3)
        
        # 3. Font formatting
        if is_bold:
            total_confidence += 25
            suggested_level = max(1, suggested_level - 1)
        
        # 4. Font family analysis
        if font_name != font_analysis["body_font_name"]:
            total_confidence += 15
        
        # 5. Position and context analysis
        # Beginning of line
        if block["x_position"] < 100:  # Left-aligned
            total_confidence += 10
        
        # 6. Content analysis - ENHANCED
        # Heavily penalize certain content types
        if any(word in text.lower() for word in ['copyright', '©', 'page', 'version']):
            total_confidence -= 40
        
        # NEW: Penalize dates more heavily
        if re.search(r'\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}', text.lower()):
            total_confidence -= 80  # Heavy penalty for dates
        
        # NEW: Penalize long sentences
        if len(text.split()) > 12 and not has_pattern:
            total_confidence -= 30
        
        # NEW: Penalize list content that's clearly not headings
        if re.match(r'^\d+\.\s+\w+.*\s+(who|that|which|are|have|will|can|may|should)', text.lower()):
            total_confidence -= 50
        
        # Boost for proper heading-like content
        if re.search(r'^(chapter|section|part|appendix)\s+', text.lower()):
            total_confidence += 30
        
        # NEW: Boost for document structure words
        structure_words = ['table of contents', 'acknowledgements', 'references', 'introduction', 'conclusion', 'overview']
        if any(word in text.lower() for word in structure_words):
            # But only if it's not repeated too much
            occurrences = sum(1 for b in self.all_text_blocks if b["text"].lower().strip() == text.lower().strip())
            if occurrences <= 2:
                total_confidence += 20
            
        # Final decision - INCREASED THRESHOLD
        is_heading = total_confidence >= 80  # Increased from 70 to be more selective
        
        # Map level to H1/H2/H3
        level_map = {1: "H1", 2: "H2", 3: "H3"}
        final_level = level_map.get(suggested_level, "H3")
        
        return is_heading, final_level, total_confidence

    def extract_title(self, text_blocks: List[Dict]) -> str:
        """Extract document title"""
        first_page_blocks = [b for b in text_blocks if b["page"] == 1]
        
        if not first_page_blocks:
            return "Untitled Document"
        
        # Filter out obvious non-titles
        title_candidates = []
        for block in first_page_blocks:
            text = block["text"].strip()
            if (len(text) > 5 and 
                not self.is_excluded_content(text, 1) and
                not re.match(r'^\d+\.', text) and  # Not numbered section
                not re.match(r'^version\s+', text.lower()) and  # Not version
                block["y_position"] < 300):  # Upper part of page (increased from 200)
                title_candidates.append(block)
        
        if not title_candidates:
            # Fallback: look for the first substantial text
            for block in first_page_blocks:
                text = block["text"].strip()
                if (len(text) > 10 and 
                    not text.lower().startswith('copyright') and
                    not re.match(r'^\d', text)):
                    return text
            return "Document"
        
        # Sort by font size (desc) then by position (asc)
        title_candidates.sort(key=lambda x: (-x["font_size"], x["y_position"]))
        
        # Take the best candidate - but prefer meaningful titles
        for candidate in title_candidates[:3]:  # Check top 3 candidates
            title = candidate["text"].strip()
            
            # Prefer titles that are not single words and not too generic
            if (len(title.split()) >= 2 and 
                title.lower() not in ['overview', 'introduction', 'document', 'foundation level']):
                # Clean up title
                title = re.sub(r'\s+', ' ', title)
                if len(title) > 100:
                    title = title[:100] + "..."
                return title
        
        # Fallback to first candidate
        title = title_candidates[0]["text"].strip()
        title = re.sub(r'\s+', ' ', title)
        if len(title) > 100:
            title = title[:100] + "..."
            
        return title

    def extract_outline(self) -> Dict:
        """Extract complete outline"""
        # Get all text blocks
        text_blocks = self.extract_text_blocks()
        self.all_text_blocks = text_blocks
        
        if not text_blocks:
            return {"title": "Empty Document", "outline": [], "metadata": {"page_count": len(self.doc)}}
        
        # Analyze fonts
        font_analysis = self.analyze_fonts(text_blocks)
        self.font_analysis = font_analysis
        
        # Extract title
        title = self.extract_title(text_blocks)
        
        # Extract headings
        headings = []
        seen_texts = set()
        
        for block in text_blocks:
            text_clean = block["text"].strip()
            if not text_clean or (text_clean.lower(), block["page"]) in seen_texts:
                continue
            is_heading, level, confidence = self.calculate_heading_likelihood(block, font_analysis)
            if is_heading:
                heading = {
                    "text": text_clean,
                    "page": block["page"],
                    "level": level,
                    "confidence": confidence,
                    "font_size": block["font_size"]
                }
                headings.append(heading)
                seen_texts.add((text_clean.lower(), block["page"]))
        
        # Sort by page and y-position
        heading_positions = {}
        for block in text_blocks:
            key = (block["text"].strip().lower(), block["page"])
            if key not in heading_positions:
                heading_positions[key] = block["y_position"]
        
        def sort_key(heading):
            key = (heading["text"].lower(), heading["page"])
            y_pos = heading_positions.get(key, 0)
            return (heading["page"], y_pos)
        
        headings.sort(key=sort_key)
        
        return {
            "title": title,
            "outline": headings,
            "metadata": {
                "page_count": len(self.doc)
            }
        }


def extract_pdf_outline(pdf_path: str) -> Dict:
    """Extract PDF outline. Returns dict with title and outline"""
    try:
        with PDFOutlineExtractor(pdf_path) as extractor:
            outline = extractor.extract_outline()
            return outline
    except Exception as e:
        print(f"Error processing PDF: {e}")
        return {"title": "Error", "outline": []}



if __name__ == "__main__":
    import sys
    import os
    
    # You can hardcode paths here for testing
    DEFAULT_PDF_PATH = r"D:\ch_1\Challenge_1a\sample_dataset\pdfs\file03.pdf"
    DEFAULT_OUTPUT_PATH = r"D:\ch_1\Challenge_1a\sample_dataset\outputs\outline3.json"
    
    # Use command line args if provided, otherwise use defaults
    if len(sys.argv) >= 2:
        pdf_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        pdf_path = DEFAULT_PDF_PATH
        output_path = DEFAULT_OUTPUT_PATH
        print(f"Using default paths:")
        print(f"PDF: {pdf_path}")
        print(f"Output: {output_path}")
    
    # Ensure output directory exists
    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)
        
    print(f"Extracting outline from: {pdf_path}")
    outline = extract_pdf_outline(pdf_path, output_path)
    
    if output_path:
        print(f"Outline saved to: {output_path}")
    else:
        print("\nExtracted Outline:")
        print(json.dumps(outline, indent=2, ensure_ascii=False))
        
    print(f"\nSummary: Found {len(outline['outline'])} headings")
    for level in ["H1", "H2", "H3"]:
        count = sum(1 for h in outline['outline'] if h['level'] == level)
        if count > 0:
            print(f"  {level}: {count} headings")
    
    # Print detailed results for review
    if outline['outline']:
        print(f"\nTitle: {outline['title']}")
        print("\nDetected headings:")
        for i, heading in enumerate(outline['outline'], 1):
            print(f"  {i:2d}. {heading['level']}: {heading['text']} (page {heading['page']})")
    
    print(f"\nFont analysis summary:")
    if hasattr(extract_pdf_outline, '_last_extractor'):
        fa = extract_pdf_outline._last_extractor.font_analysis
        print(f"  Body font size: {fa.get('body_font_size', 'N/A')}")
        print(f"  Unique font sizes: {fa.get('unique_sizes', 'N/A')}")
        print(f"  Size range: {fa.get('min_size', 'N/A')} - {fa.get('max_size', 'N/A')}")
