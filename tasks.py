"""
Async tasks for PDF generation.
Uses Celery for async processing.
"""
import os
import sys

# Add project root to Python path (for Celery worker)
PROJECT_ROOT = "/opt/grade7-new"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from celery_app import celery_app
from config import Config
from utils.pdf_utils import generate_class_reports_pdf
import logging

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def generate_class_pdf_async(self, class_id, user_id=None):
    """Async PDF generation task."""
    try:
        self.update_state(
            state='PROGRESS',
            meta={'status': '正在准备数据...', 'percent': 10}
        )
        
        # Create Flask app context (needed for Model.query)
        from app import create_app
        app = create_app()
        with app.app_context():
            # Generate PDF
            # Returns: (pdf_bytes, filename)
            pdf_bytes, filename = generate_class_reports_pdf(class_id, semester=None)
            
            # Save to file
            output_dir = os.path.join(PROJECT_ROOT, 'static', 'pdf_exports')
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, filename)
            
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)
            
            result = {
                'status': 'SUCCESS',
                'filename': filename,
                'download_url': f'/report-pdf/download/{filename}'
            }
            return result
            
    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}")
        self.update_state(
            state='FAILURE',
            meta={'status': f'生成失败: {str(e)}', 'error': str(e)}
        )
        raise
