# Copyright 2025 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import subprocess
import os
import shlex
import logging
import asyncio
from typing import Optional

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

class ExecuteRequest(BaseModel):
    """Request model for the /execute endpoint."""
    command: str
    timeout: Optional[int] = None  # Timeout in seconds, None means no timeout

class ExecuteResponse(BaseModel):
    """Response model for the /execute endpoint."""
    stdout: str
    stderr: str
    exit_code: int

class ExecuteStreamRequest(BaseModel):
    """Request model for the /execute/stream endpoint."""
    command: str
    timeout: Optional[int] = None  # Timeout in seconds, None means no timeout

app = FastAPI(
    title="Agentic Sandbox Runtime",
    description="An API server for executing commands and managing files in a secure sandbox.",
    version="1.0.0",
)

@app.get("/", summary="Health Check")
async def health_check():
    """A simple health check endpoint to confirm the server is running."""
    return {"status": "ok", "message": "Sandbox Runtime is active."}

@app.post("/execute", summary="Execute a shell command", response_model=ExecuteResponse)
async def execute_command(request: ExecuteRequest):
    """
    Executes a shell command inside the sandbox and returns its output.
    Uses shlex.split for security to prevent shell injection.
    Supports optional timeout parameter
    """
    try:
        # Split the command string into a list to safely pass to subprocess
        args = shlex.split(request.command)

        # Execute the command, always from the /app directory
        process = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd="/app",
            timeout=request.timeout
        )
        return ExecuteResponse(
            stdout=process.stdout,
            stderr=process.stderr,
            exit_code=process.returncode
        )
    except subprocess.TimeoutExpired:
        return ExecuteResponse(
            stdout="",
            stderr=f"Command timed out after {request.timeout} seconds",
            exit_code=124  # Standard timeout exit code
        )
    except Exception as e:
        return ExecuteResponse(
            stdout="",
            stderr=f"Failed to execute command: {str(e)}",
            exit_code=1
        )

@app.post("/execute/stream", summary="Execute a shell command with streaming output")
async def execute_command_stream(request: ExecuteStreamRequest):
    """
    Executes a shell command inside the sandbox and streams its output in real-time using SSE.
    Uses shlex.split for security to prevent shell injection.
    Supports optional timeout parameter (in seconds).

    The stream sends events in the following format:
    - event: stdout, data: <line from stdout>
    - event: stderr, data: <line from stderr>
    - event: done, data: {"exit_code": <code>}
    - event: error, data: <error message>
    """
    async def event_generator():
        process = None
        start_time = asyncio.get_event_loop().time()

        try:
            args = shlex.split(request.command)
            process = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd="/app"
            )

            # Stream output until process completes or timeout
            while process.returncode is None:
                # Check timeout
                if request.timeout and (asyncio.get_event_loop().time() - start_time) >= request.timeout:
                    process.kill()
                    await process.wait()
                    yield {"event": "error", "data": f"Command timed out after {request.timeout} seconds"}
                    yield {"event": "done", "data": '{"exit_code": 124}'}
                    return

                # Read from stdout
                try:
                    if line := await asyncio.wait_for(process.stdout.readline(), timeout=0.1):
                        yield {"event": "stdout", "data": line.decode('utf-8').rstrip('\n')}
                except asyncio.TimeoutError:
                    pass

                # Read from stderr
                try:
                    if line := await asyncio.wait_for(process.stderr.readline(), timeout=0.1):
                        yield {"event": "stderr", "data": line.decode('utf-8').rstrip('\n')}
                except asyncio.TimeoutError:
                    pass

                # Check if process completed
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.01)
                except asyncio.TimeoutError:
                    pass

            yield {"event": "done", "data": f'{{"exit_code": {process.returncode}}}'}

        except Exception as e:
            if process and process.returncode is None:
                try:
                    process.kill()
                    await process.wait()
                except:
                    pass
            yield {"event": "error", "data": f"Failed to execute command: {str(e)}"}
            yield {"event": "done", "data": '{"exit_code": 1}'}

    return EventSourceResponse(event_generator())

@app.post("/upload", summary="Upload a file to the sandbox")
async def upload_file(file: UploadFile = File(...)):
    """
    Receives a file and saves it to the /app directory in the sandbox.
    """
    try:
        logging.info(f"--- UPLOAD_FILE CALLED: Attempting to save '{file.filename}' ---")
        file_path = os.path.join("/app", file.filename)
        
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
        return JSONResponse(
            status_code=200,
            content={"message": f"File '{file.filename}' uploaded successfully."}
        )
    except Exception as e:
        logging.exception("An error occurred during file upload.") 
        return JSONResponse(
            status_code=500,
            content={"message": f"File upload failed: {str(e)}"}
        )

@app.get("/download/{file_path:path}", summary="Download a file from the sandbox")
async def download_file(file_path: str):
    """
    Downloads a specified file from the /app directory in the sandbox.
    """
    full_path = os.path.join("/app", file_path)
    if os.path.isfile(full_path):
        return FileResponse(path=full_path, media_type='application/octet-stream', filename=file_path)
    return JSONResponse(status_code=404, content={"message": "File not found"})