"""HTTP API server for batch processing PDFs from folders."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    from fastapi import FastAPI, HTTPException, UploadFile, File
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except ImportError:
    print("Error: FastAPI not installed. Install with: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline

app = FastAPI(
    title="Document Extraction API",
    description="API for batch processing PDFs from folders",
    version="1.0.0"
)


class ProcessFolderRequest(BaseModel):
    """Request model for processing a folder."""
    folder_path: str
    label: str
    schema_path: str
    debug: bool = False


class ProcessFolderResponse(BaseModel):
    """Response model for folder processing."""
    label: str
    schema_path: str
    folder_path: str
    total_pdfs: int
    successful: int
    errors: int
    results: List[Dict[str, Any]]
    error_details: Optional[List[Dict[str, Any]]] = None


def process_folder_internal(
    folder_path: str,
    label: str,
    schema_path: str,
    debug: bool = False,
) -> Dict[str, Any]:
    """Internal function to process folder (same logic as batch_process.py)."""
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder does not exist or is not a directory: {folder_path}")
    
    # Load schema
    schema_file = Path(schema_path)
    if not schema_file.exists():
        raise ValueError(f"Schema file does not exist: {schema_path}")
    
    schema_data = json.loads(schema_file.read_text(encoding="utf-8"))
    
    # Handle both list and dict formats
    if isinstance(schema_data, list):
        schema_dict = None
        for entry in schema_data:
            if entry.get("label") == label:
                schema_dict = entry.get("extraction_schema", {})
                break
        if schema_dict is None and schema_data:
            schema_dict = schema_data[0].get("extraction_schema", {})
        if not schema_dict:
            raise ValueError(f"Could not find extraction_schema for label '{label}' in schema file")
    elif isinstance(schema_data, dict):
        if "extraction_schema" in schema_data:
            schema_dict = schema_data["extraction_schema"]
        else:
            schema_dict = schema_data
    else:
        raise ValueError(f"Schema file must be a JSON object or array, got {type(schema_data)}")
    
    # Find all PDFs
    pdf_files = sorted(folder.glob("*.pdf"))
    if not pdf_files:
        raise ValueError(f"No PDF files found in folder: {folder_path}")
    
    # Initialize pipeline
    pipeline = Pipeline()
    
    # Process each PDF
    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    
    for pdf_path in pdf_files:
        pdf_name = pdf_path.name
        
        try:
            result = pipeline.run(label, schema_dict, str(pdf_path), debug=debug)
            
            # Add PDF name to result
            result["pdf_name"] = pdf_name
            result["pdf_path"] = str(pdf_path)
            
            results.append(result)
        except Exception as e:
            error_info = {
                "pdf_name": pdf_name,
                "pdf_path": str(pdf_path),
                "error": str(e),
                "error_type": type(e).__name__,
            }
            errors.append(error_info)
    
    # Build consolidated output
    output = {
        "label": label,
        "schema_path": str(schema_path),
        "folder_path": str(folder_path),
        "total_pdfs": len(pdf_files),
        "successful": len(results),
        "errors": len(errors),
        "results": results,
    }
    
    if errors:
        output["error_details"] = errors
    
    return output


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Document Extraction API",
        "version": "1.0.0",
        "endpoints": {
            "POST /process-folder": "Process all PDFs in a folder",
            "GET /health": "Health check",
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/process-folder", response_model=ProcessFolderResponse)
async def process_folder(request: ProcessFolderRequest):
    """Process all PDFs in a folder and return consolidated JSON.
    
    Args:
        request: ProcessFolderRequest with folder_path, label, schema_path, and optional debug flag
        
    Returns:
        ProcessFolderResponse with consolidated results for all PDFs
    """
    try:
        output = process_folder_internal(
            request.folder_path,
            request.label,
            request.schema_path,
            debug=request.debug,
        )
        return ProcessFolderResponse(**output)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.post("/process-folder-sync")
async def process_folder_sync(request: ProcessFolderRequest):
    """Process folder synchronously and return raw JSON (for compatibility)."""
    try:
        output = process_folder_internal(
            request.folder_path,
            request.label,
            request.schema_path,
            debug=request.debug,
        )
        return JSONResponse(content=output)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    
    print("Starting Document Extraction API server...")
    print("API will be available at: http://localhost:8000")
    print("API documentation at: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the server")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)

