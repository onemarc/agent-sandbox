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

import requests
import sys
import json
import time

def test_health_check(base_url):
    """
    Tests the health check endpoint.
    """
    url = f"{base_url}/"
    try:
        print(f"--- Testing Health Check endpoint ---")
        print(f"Sending GET request to {url}")
        response = requests.get(url)
        response.raise_for_status()
        print("Health check successful!")
        print("Response JSON:", response.json())
        assert response.json()["status"] == "ok"
    except (requests.exceptions.RequestException, AssertionError) as e:
        print(f"An error occurred during health check: {e}")
        sys.exit(1)

def test_execute(base_url):
    """
    Tests the execute endpoint.
    """
    url = f"{base_url}/execute"
    payload = {"command": "echo 'hello world'"}

    try:
        print(f"\n--- Testing Execute endpoint ---")
        print(f"Sending POST request to {url} with payload: {payload}")
        response = requests.post(url, json=payload)
        response.raise_for_status()  # Raise an exception for bad status codes

        print("Execute command successful!")
        print("Response JSON:", response.json())
        assert response.json()["stdout"] == "hello world\n"

    except (requests.exceptions.RequestException, AssertionError) as e:
        print(f"An error occurred during execute command: {e}")
        sys.exit(1)

def test_execute_timeout(base_url):
    """
    Tests the execute endpoint with timeout functionality.
    """
    url = f"{base_url}/execute"
    payload = {"command": "sleep 5", "timeout": 2}

    try:
        print(f"\n--- Testing Execute endpoint with timeout ---")
        print(f"Sending POST request to {url} with payload: {payload}")
        print("This should timeout after 2 seconds...")
        response = requests.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        print("Response JSON:", result)

        # Verify that the command timed out
        assert result["exit_code"] == 124, "Expected exit code 124 for timeout"
        assert "timed out" in result["stderr"].lower(), "Expected timeout message in stderr"
        print("Timeout test successful!")

    except (requests.exceptions.RequestException, AssertionError) as e:
        print(f"An error occurred during timeout test: {e}")
        sys.exit(1)

def test_execute_stream(base_url):
    """
    Tests the execute/stream endpoint with SSE.
    """
    url = f"{base_url}/execute/stream"
    # Use a command that produces multiple lines of output over time
    payload = {"command": "sh -c 'for i in 1 2 3; do echo Line $i; sleep 0.5; done'"}

    try:
        print(f"\n--- Testing Execute Stream endpoint ---")
        print(f"Sending POST request to {url} with payload: {payload}")
        print("Streaming output:")

        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()

        stdout_lines = []
        exit_code = None

        # Parse SSE stream
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('event: '):
                    event_type = line_str.split(': ', 1)[1]
                elif line_str.startswith('data: '):
                    data = line_str.split(': ', 1)[1]

                    if event_type == 'stdout':
                        print(f"  [stdout] {data}")
                        stdout_lines.append(data)
                    elif event_type == 'stderr':
                        print(f"  [stderr] {data}")
                    elif event_type == 'done':
                        exit_data = json.loads(data)
                        exit_code = exit_data['exit_code']
                        print(f"  [done] Exit code: {exit_code}")
                    elif event_type == 'error':
                        print(f"  [error] {data}")

        # Verify we got the expected output
        assert len(stdout_lines) == 3, f"Expected 3 stdout lines, got {len(stdout_lines)}"
        assert exit_code == 0, f"Expected exit code 0, got {exit_code}"
        print("Stream test successful!")

    except (requests.exceptions.RequestException, AssertionError) as e:
        print(f"An error occurred during stream test: {e}")
        sys.exit(1)

def test_execute_stream_timeout(base_url):
    """
    Tests the execute/stream endpoint with timeout.
    """
    url = f"{base_url}/execute/stream"
    payload = {"command": "sleep 10", "timeout": 2}

    try:
        print(f"\n--- Testing Execute Stream endpoint with timeout ---")
        print(f"Sending POST request to {url} with payload: {payload}")
        print("This should timeout after 2 seconds...")

        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()

        exit_code = None
        got_timeout_error = False

        # Parse SSE stream
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('event: '):
                    event_type = line_str.split(': ', 1)[1]
                elif line_str.startswith('data: '):
                    data = line_str.split(': ', 1)[1]

                    if event_type == 'error':
                        print(f"  [error] {data}")
                        if "timed out" in data.lower():
                            got_timeout_error = True
                    elif event_type == 'done':
                        exit_data = json.loads(data)
                        exit_code = exit_data['exit_code']
                        print(f"  [done] Exit code: {exit_code}")

        # Verify timeout occurred
        assert got_timeout_error, "Expected timeout error message"
        assert exit_code == 124, f"Expected exit code 124 for timeout, got {exit_code}"
        print("Stream timeout test successful!")

    except (requests.exceptions.RequestException, AssertionError) as e:
        print(f"An error occurred during stream timeout test: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python tester.py <server_ip> <server_port>")
        sys.exit(1)

    ip = sys.argv[1]
    port = sys.argv[2]
    base_url = f"http://{ip}:{port}"

    # Run all tests
    test_health_check(base_url)
    test_execute(base_url)
    test_execute_timeout(base_url)
    test_execute_stream(base_url)
    test_execute_stream_timeout(base_url)

    print("\n" + "="*50)
    print("All tests passed successfully!")
    print("="*50)
