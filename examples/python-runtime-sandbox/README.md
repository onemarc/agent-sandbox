# Python Runtime Sandbox

This example implements a simple Python server in a sandbox container. 
It includes a FastAPI server that can execute commands and a Python script to test it (`tester.py`).

Test it out by running `run-test-docker`:
It will build a (local) container image containing the python server,run it, then execute `tester.py` to test the running container and a cleanup.

The `tester.py` script acts as a client to interact with the python API server, sending a command to the `/execute` endpoint and printing the standard output, standard error, and exit code from the response.

Usage:
`python tester.py [ip] [port]`

## API Endpoints

The Python Runtime Sandbox provides several endpoints for interacting with the sandbox:

### Health Check: `GET /`
Simple health check endpoint to confirm the server is running.

**Response:**
```json
{"status": "ok", "message": "Sandbox Runtime is active."}
```

### Execute Command: `POST /execute`
Executes a shell command and returns the complete output after execution.

**Request Body:**
```json
{
  "command": "echo 'hello world'",
  "timeout": 30  // Optional: timeout in seconds
}
```

**Response:**
```json
{
  "stdout": "hello world\n",
  "stderr": "",
  "exit_code": 0
}
```

### Execute Command (Streaming): `POST /execute/stream`
Executes a shell command and streams the output in real-time using Server-Sent Events (SSE). This is ideal for long-running commands where you want to see output as it's generated.

**Request Body:**
```json
{
  "command": "sh -c 'for i in 1 2 3; do echo Line $i; sleep 1; done'",
  "timeout": 60  // Optional: timeout in seconds
}
```

**SSE Event Stream:**
The endpoint returns an SSE stream with the following event types:
- `stdout`: A line of standard output
- `stderr`: A line of standard error
- `error`: An error message (e.g., timeout)
- `done`: Command completed, includes exit code as JSON `{"exit_code": 0}`

**Example Python client:**
```python
import requests
import json

response = requests.post(
    "http://localhost:8000/execute/stream",
    json={"command": "echo hello", "timeout": 30},
    stream=True
)

for line in response.iter_lines():
    if line:
        line_str = line.decode('utf-8')
        if line_str.startswith('event: '):
            event_type = line_str.split(': ', 1)[1]
        elif line_str.startswith('data: '):
            data = line_str.split(': ', 1)[1]
            if event_type == 'stdout':
                print(f"Output: {data}")
            elif event_type == 'done':
                exit_data = json.loads(data)
                print(f"Exit code: {exit_data['exit_code']}")
```

### Upload File: `POST /upload`
Uploads a file to the `/app` directory in the sandbox.

### Download File: `GET /download/{file_path}`
Downloads a file from the `/app` directory in the sandbox.

## Timeout Support

Both `/execute` and `/execute/stream` endpoints support an optional `timeout` parameter (in seconds):
- If a command exceeds the timeout, it will be terminated
- The endpoint will return exit code `124` (standard timeout exit code)
- For streaming, you'll receive an error event before the done event

**Example with timeout:**
```python
# This will timeout after 2 seconds
response = requests.post(
    "http://localhost:8000/execute",
    json={"command": "sleep 10", "timeout": 2}
)
print(response.json())
# {"stdout": "", "stderr": "Command timed out after 2 seconds", "exit_code": 124}
```

## Python Classes in `main.py`

The `main.py` file defines the following Pydantic models to ensure type-safe data for the API endpoints:

### `ExecuteRequest`
Request model for the `/execute` endpoint.
- **`command: str`**: The shell command to be executed in the sandbox.
- **`timeout: Optional[int]`**: Optional timeout in seconds (default: None).

### `ExecuteResponse`
Response model for the `/execute` endpoint.
- **`stdout: str`**: The standard output from the executed command.
- **`stderr: str`**: The standard error from the executed command.
- **`exit_code: int`**: The exit code of the executed command.

### `ExecuteStreamRequest`
Request model for the `/execute/stream` endpoint.
- **`command: str`**: The shell command to be executed in the sandbox.
- **`timeout: Optional[int]`**: Optional timeout in seconds (default: None).

## Testing on a local kind cluster using agent-sandbox

To test the sandbox on a local [kind](https://kind.sigs.k8s.io/) cluster, you can use the `run-test-kind.sh` script.
This script will:
1.  Create a kind cluster (if it doesn't exist).
2.  Build and deploy the agent sandbox controller to the cluster.
3.  Build the python runtime sandbox image.
4.  Load the image into the kind cluster.
5.  Deploy the sandbox and run the tests using examples/python-runtime-sandbox/sandbox-python-kind.yaml
6.  Clean up all the resources.

To run the script:
```bash
./run-test-kind.sh
```
