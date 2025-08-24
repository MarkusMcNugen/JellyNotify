#!/usr/bin/env python3
"""
Test script to verify static file serving is working correctly.
Run this after deploying to Docker to check if assets are being served.
"""

import requests
import sys

def test_static_files(base_url="http://localhost:1985"):
    """Test that static files are being served correctly"""
    
    print(f"Testing static file serving at {base_url}")
    print("-" * 50)
    
    # Test endpoints
    tests = [
        ("/", "text/html", "index.html"),
        ("/api/health", "application/json", "API health"),
        ("/assets/index-BdASS8Ro.css", "text/css", "CSS file"),
        ("/assets/index-Brl9qVFk.js", "application/javascript", "JS file"),
    ]
    
    results = []
    
    for path, expected_type, description in tests:
        url = f"{base_url}{path}"
        print(f"\nTesting {description}: {url}")
        
        try:
            response = requests.get(url, timeout=5)
            content_type = response.headers.get('content-type', '').split(';')[0]
            
            print(f"  Status: {response.status_code}")
            print(f"  Content-Type: {content_type}")
            
            if response.status_code == 200:
                if expected_type in content_type:
                    print(f"  ✓ SUCCESS: Correct content type")
                    results.append(True)
                else:
                    print(f"  ✗ FAIL: Expected {expected_type}, got {content_type}")
                    results.append(False)
            else:
                print(f"  ✗ FAIL: HTTP {response.status_code}")
                if response.headers.get('content-type') == 'application/json':
                    print(f"  Response: {response.json()}")
                results.append(False)
                
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append(False)
    
    print("\n" + "=" * 50)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    
    if all(results):
        print("✓ All tests passed! Static file serving is working correctly.")
        return 0
    else:
        print("✗ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    # Allow custom URL from command line
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:1985"
    exit_code = test_static_files(url)
    sys.exit(exit_code)