"""
PDF extraction modules for the TOC extractor.

This package contains different extractor implementations that can be used
to extract text and structural information from PDF documents.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path

class BaseExtractor(ABC):
    """Base class for all PDF extractors."""
    
    @abstractmethod
    def extract_toc(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract table of contents from a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of dictionaries containing TOC entries with keys:
            - text: The heading text
            - page: Page number (1-based)
            - font_size: Font size (optional)
            - is_bold: Whether the text is bold (optional)
            - confidence: Confidence score (0-1)
        """
        pass
    
    @abstractmethod
    def extract_title(self, pdf_path: str) -> str:
        """
        Extract the title of the PDF document.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            The extracted title or an empty string if not found
        """
        pass

# Import PDFOutlineExtractor implementation
from .robust_extractor import PDFOutlineExtractor

# Default extractor to use
DEFAULT_EXTRACTOR = PDFOutlineExtractor

__all__ = [
    'BaseExtractor',
    'PDFOutlineExtractor',
    'DEFAULT_EXTRACTOR'
]
