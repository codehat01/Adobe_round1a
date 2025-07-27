import os
import sys
import json
from jsonschema import validate, ValidationError
from pathlib import Path
from multiprocessing import Pool, cpu_count
import multiprocessing
from functools import partial
import logging
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm 
# Logger setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load JSON schema
schema_path = Path(__file__).parent / "app" / "schema" / "output_schema.json"
try:
    OUTPUT_SCHEMA = json.loads(schema_path.read_text(encoding="utf-8"))
except FileNotFoundError:
    OUTPUT_SCHEMA = None
    logger.warning("Output schema file not found – validation disabled.")

# Add app to path
project_root = Path(__file__).parent.resolve()
app_dir = project_root / "app"
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from app.extractor.robust_extractor import extract_pdf_outline

def process_one_pdf(pdf_path, output_dir):
    try:
        result = extract_pdf_outline(str(pdf_path))
        # Remove unwanted fields from each outline entry
        clean_outline = []
        for h in result.get("outline", []):
            clean_outline.append({k: v for k, v in h.items() if k not in {"font_size", "confidence"}})
        clean_result = {
            "title": result.get("title"),
            "outline": clean_outline,
            "metadata": result.get("metadata", {})
        }

        # Validate against JSON schema if available
        if OUTPUT_SCHEMA:
            try:
                validate(instance=clean_result, schema=OUTPUT_SCHEMA)
            except ValidationError as ve:
                logger.error(f"Schema validation failed for {pdf_path.name}: {ve}")
                return {"file": str(pdf_path), "status": "error", "error": f"Schema validation failed: {ve}"}

        output_path = output_dir / (pdf_path.stem + ".json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(clean_result, f, indent=2, ensure_ascii=False)
        return {"file": str(pdf_path), "status": "success", "outline": clean_outline, "metadata": result.get("metadata", {})}
    except Exception as e:
        return {"file": str(pdf_path), "status": "error", "error": str(e)}

def process_pdfs(input_dir: str = None, output_dir: str = None, workers: int = None):
    """Process PDFs in parallel
    
    Args:
        input_dir: Directory containing PDFs to process (default: ./sample_dataset/pdfs)
        output_dir: Directory to save output JSON files (default: ./sample_dataset/outputs)
        workers: Number of worker processes to use (default: number of CPU cores - 1)
    """
    # Set defaults
    base_dir = Path(__file__).parent
    input_dir = Path(input_dir) if input_dir else base_dir / "app" / "input"
    output_dir = Path(output_dir) if output_dir else base_dir / "app" / "output"
    logs_dir = base_dir / "app" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find PDFs
    pdf_files = list(input_dir.glob("*.pdf"))
    
    if not pdf_files:
        logger.warning(f"No PDF files found in {input_dir}")
        return []
    
    # Worker count
    if workers is None:
        workers = max(1, multiprocessing.cpu_count() - 1)
    
    logger.info(f"Processing {len(pdf_files)} PDFs using {workers} workers...")
    
    # Stats setup
    stats = {
        "total_files": len(pdf_files),
        "successful": 0,
        "failed": 0,
        "total_entries": 0,
        "processing_times": []
    }
    
    # Parallel processing
    results = []
    start_time = datetime.now()
    
    with ProcessPoolExecutor(max_workers=workers) as executor:
        # Submit all tasks
        future_to_pdf = {}
        file_times = {}
        for pdf_file in pdf_files:
            file_times[pdf_file] = {"start": datetime.now()}
            future = executor.submit(process_one_pdf, pdf_file, output_dir)
            future_to_pdf[future] = pdf_file
        
        # Handle results
        with tqdm(total=len(pdf_files), desc="Processing PDFs") as pbar:
            for future in as_completed(future_to_pdf):
                pdf_file = future_to_pdf[future]
                file_times[pdf_file]["end"] = datetime.now()
                try:
                    result = future.result()
                    results.append(result)
                    # Logging uses data saved by worker; no re-save here to avoid overwriting correct JSON
                    output_file = output_dir / f"{pdf_file.stem}.json"
                    if not output_file.exists():
                        # fallback if worker failed to write
                        with open(output_file, 'w', encoding='utf-8') as f:
                            json.dump({k: v for k, v in result.items() if k not in {"file", "status"}}, f, indent=2, ensure_ascii=False)
                    # Save detailed log in logs dir (user format)
                    log_file = logs_dir / f"{pdf_file.stem}.log.json"
                    start_time = file_times[pdf_file]["start"]
                    end_time = file_times[pdf_file]["end"]
                    processing_seconds = (end_time - start_time).total_seconds()
                    outline = result.get("outline", [])
                    log_event = {
                        "filename": pdf_file.name,
                        "page_count": result.get("metadata", {}).get("page_count", None),
                        "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        "end_time": end_time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        "duration_seconds": round(processing_seconds, 3),
                        "sections_extracted": len(outline) if isinstance(outline, list) else 0,
                        "success": result.get("status") == "success"
                    }
                    with open(log_file, 'w', encoding='utf-8') as f:
                        json.dump({"log_event": log_event}, f, indent=2, ensure_ascii=False)
                    # Update progress and statistics
                    if result["status"] == "success":
                        stats["successful"] += 1
                        stats["total_entries"] += len(outline)
                        logger.info(f"Processed {pdf_file.name} - {len(outline)} entries")

                        # Show a preview of the first few entries
                        if outline:
                            print("\n   First few TOC entries:")
                            for entry in outline[:3]:
                                print(f"     {entry.get('level', '?')} (p{entry.get('page', '?')}): {entry.get('text', '')}")
                            if len(outline) > 3:
                                print(f"     ... and {len(outline) - 3} more entries")
                        print(f"- {pdf_file.name}: {len(outline)} entries")
                    else:
                        stats["successful"] += 1
                        stats["total_entries"] += len(outline)
                        logger.info(f"Processed {pdf_file.name} - {len(outline)} entries")
                        stats["failed"] += 1
                        print("\n" + "!"*80)
                        print(f"❌ FAILED: {pdf_file.name}")
                        print("-" * 80)
                        print(f"Error: {result.get('error', 'Unknown error')}")
                        print("!"*80)
                
                except Exception as e:
                    stats["failed"] += 1
                    error_msg = f"Unexpected error processing {pdf_file.name}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    print(f"\n❌ Error: {error_msg}")
                
                pbar.update(1)
    
    # Calc time
    total_time = (datetime.now() - start_time).total_seconds()
    
    # Print final statistics
    print("\n" + "="*80)
    print("📊 PROCESSING SUMMARY")
    print("="*80)
    
    # Summary table
    print(f"{'Total PDFs:':<20} {stats['total_files']}")
    print(f"{'✅ Successful:':<20} {stats['successful']}")
    print(f"{'❌ Failed:':<20} {stats['failed']}")
    print(f"{'📋 Total Entries:':<20} {stats['total_entries']}")
    print(f"{'⏱️  Total Time:':<20} {total_time:.2f}s")
    
    if stats['successful'] > 0:
        avg_time = total_time / stats['successful']
        print(f"{'⏱️  Avg Time/File:':<20} {avg_time:.2f}s")
    
    # Show failed files if any
    if stats['failed'] > 0:
        print("\n" + "!"*40)
        print("❌ Failed Files:")
        print("!"*40)
        for result in results:
            if result.get('status') == 'error':
                print(f"- {result['file']}: {result.get('error', 'Unknown error')}")
    
    # Show successful files summary
    if stats['successful'] > 0:
        print("\n" + "✓"*40)
        print("✅ Successfully Processed:")
        print("✓"*40)
        for result in results:
            if result.get('status') == 'success':
                print(f"- {result.get('file', 'UNKNOWN')}: {len(result.get('outline', []))} entries")
    
    print("\n" + "="*80)
    print("🎉 PROCESSING COMPLETE!")
    print("="*80)
    print(f"💾 Output Directory: {output_dir}")
    print(f"📋 Log File: {os.path.abspath('pdf_processor.log')}")
    print("\nThank you for using the PDF Processor! 🚀")
    
    return results

def parse_arguments():
    import argparse
    
    # Default paths
    base_dir = os.path.dirname(__file__)
    default_input_dir = os.path.join(base_dir, "app", "input")
    default_output_dir = os.path.join(base_dir, "app", "output")
    
    parser = argparse.ArgumentParser(description='PDF TOC Extractor - Extract and process table of contents from PDF files')
    
    # Processing mode
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--serve', action='store_true',
                          help='Start the API server (default: process files in batch mode)')
    
    # API server options
    server_group = parser.add_argument_group('API Server Options')
    server_group.add_argument('--host', type=str, default='0.0.0.0',
                            help='Host to bind the API server to (default: 0.0.0.0)')
    server_group.add_argument('--port', type=int, default=8000,
                            help='Port to bind the API server to (default: 8000)')
    
    # Batch processing options
    batch_group = parser.add_argument_group('Batch Processing Options')
    batch_group.add_argument('-i', '--input-dir', type=str, default=default_input_dir,
                           help=f'Input directory containing PDFs (default: {default_input_dir})')
    batch_group.add_argument('-o', '--output-dir', type=str, default=default_output_dir,
                           help=f'Output directory for JSON files (default: {default_output_dir})')
    batch_group.add_argument('-w', '--workers', type=int, 
                           help=f'Number of worker processes (default: CPU cores - 1)')
    
    # General options
    general_group = parser.add_argument_group('General Options')
    general_group.add_argument('-v', '--verbose', action='store_true',
                             help='Enable verbose output')
    general_group.add_argument('--min-confidence', type=float, default=0.3,
                             help='Minimum confidence score for TOC entries (0-1, default: 0.3)')
    
    return parser.parse_args()

def run_server(host: str = '0.0.0.0', port: int = 8000):
    """Run the FastAPI server if FastAPI is available."""
    if not FASTAPI_AVAILABLE:
        print("\n" + "="*80)
        print("❌ FastAPI is not available. Cannot start the API server.")
        print("Please install FastAPI and uvicorn to use the web interface:")
        print("pip install fastapi uvicorn")
        print("="*80 + "\n")
        return
        
    import uvicorn
    
    print("\n" + "="*80)
    print("🚀 PDF TOC Extractor API Server")
    print("="*80)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API Docs: http://{host}:{port}/docs")
    print("="*80 + "\n")
    
    uvicorn.run(app, host=host, port=port)

def run_batch_processing(args):
    """Run batch processing of PDF files."""
    print("\n" + "="*80)
    print("📚 PDF TOC Extractor - Batch Processing Mode")
    print("="*80)
    print(f"Input directory: {args.input_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Workers: {args.workers or 'auto'}")
    print(f"Min confidence: {args.min_confidence}")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    start_time = datetime.now()
    
    try:
        # Process PDFs with provided arguments
        results = process_pdfs(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            workers=args.workers
        )
        
        # Exit with appropriate status code
        if results and any(r.get('status') == 'error' for r in results):
            sys.exit(1)  # Some files failed
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"A critical error occurred: {str(e)}", exc_info=True)
        print(f"\n❌ Processing failed: {str(e)}")
        sys.exit(1)
    finally:
        total_time = (datetime.now() - start_time).total_seconds()
        print(f"\nTotal processing time: {total_time:.2f} seconds")
        print(f"Log file: {os.path.abspath('pdf_processor.log')}")
        print("\n" + "="*80)
        print("✅ Processing completed" + " " * 20)
        print("="*80 + "\n")

if __name__ == "__main__":
    # Parse command line arguments
    args = parse_arguments()
    
    # Configure logging level based on verbosity
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger.setLevel(log_level)
    
    # Run in the appropriate mode
    if args.serve:
        run_server(host=args.host, port=args.port)
    else:
        run_batch_processing(args)
