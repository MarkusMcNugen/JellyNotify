#!/usr/bin/env python3
"""
Test the web interface with Playwright to diagnose content loading issues.
Captures console logs and checks if API calls are being made.
"""

from playwright.sync_api import sync_playwright
import time
import json

def test_web_interface():
    with sync_playwright() as p:
        # Launch browser in headed mode to see what's happening
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Collect console messages
        console_messages = []
        page.on("console", lambda msg: console_messages.append({
            "type": msg.type,
            "text": msg.text,
            "location": msg.location
        }))
        
        # Collect network requests
        api_requests = []
        def log_request(request):
            if '/api/' in request.url:
                api_requests.append({
                    "url": request.url,
                    "method": request.method,
                    "headers": dict(request.headers)
                })
        page.on("request", log_request)
        
        # Collect network responses
        api_responses = []
        def log_response(response):
            if '/api/' in response.url:
                api_responses.append({
                    "url": response.url,
                    "status": response.status,
                    "ok": response.ok
                })
        page.on("response", log_response)
        
        print("=" * 80)
        print("Testing Web Interface at http://192.168.1.219:1985/")
        print("=" * 80)
        
        # Navigate to the main page
        print("\n1. Loading main page...")
        page.goto("http://192.168.1.219:1985/", wait_until="networkidle")
        
        # Wait a bit for React to render
        time.sleep(3)
        
        # Check page title and content
        title = page.title()
        print(f"   Page title: {title}")
        
        # Look for key elements that should be present
        print("\n2. Checking for key UI elements...")
        
        # Check navigation
        nav_items = page.query_selector_all("nav a")
        print(f"   Navigation items found: {len(nav_items)}")
        for item in nav_items:
            text = item.inner_text()
            href = item.get_attribute("href")
            print(f"      - {text}: {href}")
        
        # Check if main content area exists
        main_content = page.query_selector("main")
        if main_content:
            print("   Main content area: Found")
            content_text = main_content.inner_text()
            print(f"   Content length: {len(content_text)} characters")
            if len(content_text) < 500:
                print(f"   Content preview: {content_text[:200]}")
        else:
            print("   Main content area: NOT FOUND")
        
        # Check for specific Overview page elements
        print("\n3. Checking Overview page elements...")
        dashboard_header = page.query_selector("h1")
        if dashboard_header:
            print(f"   Dashboard header: {dashboard_header.inner_text()}")
        
        # Look for statistics cards
        stat_cards = page.query_selector_all(".bg-white.rounded-lg.shadow")
        print(f"   Statistics cards found: {len(stat_cards)}")
        
        # Check for loading spinner
        spinner = page.query_selector(".animate-spin")
        if spinner:
            print("   ⚠️ Loading spinner is still visible!")
        
        # Check for error messages
        error_divs = page.query_selector_all(".bg-red-50, .bg-red-900")
        if error_divs:
            print(f"   ⚠️ Error messages found: {len(error_divs)}")
            for err in error_divs:
                print(f"      - {err.inner_text()}")
        
        print("\n4. Console Messages:")
        print(f"   Total console messages: {len(console_messages)}")
        
        # Filter and display important messages
        for msg in console_messages[-20:]:  # Last 20 messages
            if "logger.js" in str(msg.get("location", "")):
                print(f"   [{msg['type']}] {msg['text']}")
        
        print("\n5. API Requests Made:")
        print(f"   Total API requests: {len(api_requests)}")
        for req in api_requests:
            print(f"   - {req['method']} {req['url']}")
        
        print("\n6. API Responses:")
        print(f"   Total API responses: {len(api_responses)}")
        for resp in api_responses:
            status_icon = "✓" if resp['ok'] else "✗"
            print(f"   {status_icon} {resp['status']} {resp['url']}")
        
        # Navigate to other pages to test
        print("\n7. Testing other pages...")
        
        # Test Config page
        print("\n   Testing /config page...")
        page.goto("http://192.168.1.219:1985/config", wait_until="networkidle")
        time.sleep(2)
        config_header = page.query_selector("h1")
        if config_header:
            print(f"   Config header: {config_header.inner_text()}")
        config_content = page.query_selector("main")
        if config_content:
            print(f"   Config content length: {len(config_content.inner_text())} characters")
        
        # Test Templates page
        print("\n   Testing /templates page...")
        page.goto("http://192.168.1.219:1985/templates", wait_until="networkidle")
        time.sleep(2)
        templates_header = page.query_selector("h2")
        if templates_header:
            print(f"   Templates header: {templates_header.inner_text()}")
        template_list = page.query_selector_all(".bg-dark-surface")
        print(f"   Template sections found: {len(template_list)}")
        
        # Test Logs page
        print("\n   Testing /logs page...")
        page.goto("http://192.168.1.219:1985/logs", wait_until="networkidle")
        time.sleep(2)
        logs_header = page.query_selector("h2")
        if logs_header:
            print(f"   Logs header: {logs_header.inner_text()}")
        
        # Go back to overview and check console for errors
        print("\n8. Returning to Overview page...")
        page.goto("http://192.168.1.219:1985/", wait_until="networkidle")
        time.sleep(2)
        
        # Take a screenshot for debugging
        page.screenshot(path="web_interface_debug.png")
        print("\n   Screenshot saved to web_interface_debug.png")
        
        # Get final console messages
        print("\n9. Final Console Messages (last 10):")
        for msg in console_messages[-10:]:
            print(f"   [{msg['type']}] {msg['text'][:200]}")
        
        # Check localStorage for auth status
        print("\n10. Checking localStorage:")
        auth_status = page.evaluate("() => localStorage.getItem('auth_enabled')")
        access_token = page.evaluate("() => localStorage.getItem('access_token')")
        print(f"   auth_enabled: {auth_status}")
        print(f"   has access_token: {bool(access_token)}")
        
        browser.close()
        
        print("\n" + "=" * 80)
        print("Test Complete")
        print("=" * 80)

if __name__ == "__main__":
    test_web_interface()