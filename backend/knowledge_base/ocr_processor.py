"""OCR processing for images with text.

References:
- Requirements 16: Document Processing
- Design Section 14.2: Supported File Types
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Result of OCR processing."""
    
    text: str
    confidence: float
    language: str
    processing_time: float
    image_size: tuple[int, int]


class OCRProcessor:
    """Process images with OCR to extract text."""
    
    def __init__(self, language: str = 'eng+chi_sim'):
        """Initialize OCR processor.
        
        Args:
            language: Tesseract language codes (e.g., 'eng', 'chi_sim', 'eng+chi_sim')
        """
        self.language = language
        logger.info(f"OCRProcessor initialized with language: {language}")
    
    def process(self, image_path: Path) -> OCRResult:
        """Extract text from image using OCR.
        
        Args:
            image_path: Path to image file
            
        Returns:
            OCRResult with extracted text and confidence
        """
        start_time = datetime.now()
        
        try:
            # Open image
            image = Image.open(image_path)
            image_size = image.size
            
            # Perform OCR
            text = pytesseract.image_to_string(image, lang=self.language)
            
            # Get confidence scores
            data = pytesseract.image_to_data(image, lang=self.language, output_type=pytesseract.Output.DICT)
            confidences = [int(conf) for conf in data['conf'] if conf != '-1']
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                "OCR processing completed",
                extra={
                    "file": str(image_path),
                    "confidence": avg_confidence,
                    "text_length": len(text),
                    "time": processing_time,
                }
            )
            
            return OCRResult(
                text=text,
                confidence=avg_confidence / 100.0,  # Normalize to 0-1
                language=self.language,
                processing_time=processing_time,
                image_size=image_size,
            )
            
        except Exception as e:
            logger.error(f"OCR processing failed: {e}", exc_info=True)
            raise


# Singleton instance
_ocr_processor: Optional[OCRProcessor] = None


def get_ocr_processor(language: str = 'eng+chi_sim') -> OCRProcessor:
    """Get or create the OCR processor singleton.
    
    Args:
        language: Tesseract language codes
        
    Returns:
        OCRProcessor instance
    """
    global _ocr_processor
    if _ocr_processor is None:
        _ocr_processor = OCRProcessor(language=language)
    return _ocr_processor
