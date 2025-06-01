import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import getpass
import os
import time
import argparse
import subprocess
import re

def get_major_version(command):
    try:
        result = subprocess.run([command, '--version'], capture_output=True, text=True, check=True)
        version_match = re.search(r'([0-9]+\.)+[0-9]+', result.stdout)
        if version_match:
            version_string = version_match.group(0)
            major_version = version_string.split('.')[0]
            return int(major_version)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def main():
    driver = None
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Fetch Deepseek chat sessions and save to JSON.')
        parser.add_argument('--output', '-o', default='chat_data.json',
                            help='Path to the output JSON file (default: chat_data.json)')
        args = parser.parse_args()
        output_path = args.output

        # Check for existing data
        existing_sessions = {}
        if os.path.exists(output_path):
            try:
                with open(output_path, 'r') as f:
                    existing_data = json.load(f)
                    if isinstance(existing_data, list):
                        for entry in existing_data:
                            chat_session = entry.get('chat_session', {})
                            session_id = chat_session.get('id')
                            if session_id:
                                existing_sessions[session_id] = entry
                        print(f"Loaded {len(existing_sessions)} existing entries.")
                    else:
                        print(f"Warning: Existing file {output_path} is not a JSON array. Starting fresh.")
            except Exception as e:
                print(f"Warning: Could not read existing file {output_path}: {str(e)}. Starting fresh.")

        # Prep Chromium
        options = uc.ChromeOptions()
        dataDir = f"/home/{getpass.getuser()}/.config/chromium"
        if not os.path.isdir(dataDir):
            dataDir = f"/home/{getpass.getuser()}/.config/google-chrome"
        if os.path.isdir(dataDir):
            options.add_argument(f"--profile-directory=Default")
        for cmd in ['chromium-browser', 'google-chrome']:
            major_version = get_major_version(cmd)
            if major_version:
                break
        else:
            print("Neither chromium-browser nor google-chrome is available.")
        driver = uc.Chrome(options=options, user_data_dir=dataDir, version_main=major_version)

        # Wait for manual login
        driver.get("https://chat.deepseek.com")
        WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((uc.By.CSS_SELECTOR, "#chat-input"))
        )

        # Grab all chat session entry data
        session_summary_entries = []
        has_more = True
        params = None
        while has_more:
            script_to_run="""
                const params = arguments[0];
                let url = '/api/v0/chat_session/fetch_page';
                if (params) {
                    url += '?' + new URLSearchParams(params).toString();
                }
                return fetch(url, {
                    method: 'GET',
                    credentials: 'include',
                    headers: {
                        Authorization: 'Bearer ' + JSON.parse(localStorage.getItem('userToken')).value,
                        accept: '*/*',
                        "accept-language": 'en-US,en;q=0.9',
                        priority: 'u=1, i',
                        referer: 'https://chat.deepseek.com/',
                        "sec-ch-ua": '"Not.A/Brand";v="99", "Chromium";v="136"',
                        "sec-ch-ua-arch": '"x86"',
                        "sec-ch-ua-bitness": '"64"',
                        "sec-ch-ua-full-version": '"136.0.7103.113"',
                        "sec-ch-ua-full-version-list": '"Not.A/Brand";v="99.0.0.0", "Chromium";v="136.0.7103.113"',
                        "sec-ch-ua-mobile": '?0',
                        "sec-ch-ua-model": '""',
                        "sec-ch-ua-platform": '"Linux"',
                        "sec-ch-ua-platform-version": '"6.14.6"',
                        "sec-fetch-dest": 'empty',
                        "sec-fetch-mode": 'cors',
                        "sec-fetch-site": 'same-origin',
                        "user-agent": 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
                        "x-app-version": '20241129.1',
                        "x-client-locale": 'en_US',
                        "x-client-platform": 'web',
                        "x-client-version": '1.2.0-sse-hint'
                    }
                })
                .then(res => res.json())
                .catch(err => ({ error: err.message }));
            """
            print(script_to_run)
            response = driver.execute_script(script_to_run, params)

            if 'error' in response:
                raise Exception(f"API Error: {response['error']}")

            biz_data = response.get('data', {}).get('biz_data', {})
            sessions = biz_data.get('chat_sessions', [])
            has_more = biz_data.get('has_more', False)
            
            session_summary_entries.extend(sessions)
            
            if has_more and sessions:
                last_seq = sessions[-1].get('seq_id')
                params = {'before_seq_id': last_seq}
            else:
                params = None
        session_summary_entries_len = len(session_summary_entries)
        print(f"Found {session_summary_entries_len} chat sessions.")
        if (session_summary_entries_len == 0):
            exit()
        print(f"Fetching messages...")

        # Grab session data, reusing existing entries where timestamps are current
        session_data_entries = []
        for idx, session in enumerate(session_summary_entries):
            session_id = session.get('id')
            if not session_id:
                continue

            server_updated_at = session.get('updated_at', 0.0)
            existing_entry = existing_sessions.get(session_id)
            
            if existing_entry:
                existing_updated_at = existing_entry.get('chat_session', {}).get('updated_at', 0.0)
                if server_updated_at <= existing_updated_at:
                    session_data_entries.append(existing_entry)
                    print(f"Session {idx+1}/{session_summary_entries_len} (ID: {session_id}) loaded from cache (up to date).")
                    continue

            # Fetch new session data
            response = driver.execute_script("""
                const sessionId = arguments[0];
                return fetch(`/api/v0/chat/history_messages?chat_session_id=${sessionId}`, {
                    method: 'GET',
                    credentials: 'include',
                    headers: {
                        Authorization: 'Bearer ' + JSON.parse(localStorage.getItem('userToken')).value,
                        accept: '*/*',
                        "accept-language": 'en-US,en;q=0.9',
                        priority: 'u=1, i',
                        referer: 'https://chat.deepseek.com/',
                        "sec-ch-ua": '"Not.A/Brand";v="99", "Chromium";v="136"',
                        "sec-ch-ua-arch": '"x86"',
                        "sec-ch-ua-bitness": '"64"',
                        "sec-ch-ua-full-version": '"136.0.7103.113"',
                        "sec-ch-ua-full-version-list": '"Not.A/Brand";v="99.0.0.0", "Chromium";v="136.0.7103.113"',
                        "sec-ch-ua-mobile": '?0',
                        "sec-ch-ua-model": '""',
                        "sec-ch-ua-platform": '"Linux"',
                        "sec-ch-ua-platform-version": '"6.14.6"',
                        "sec-fetch-dest": 'empty',
                        "sec-fetch-mode": 'cors',
                        "sec-fetch-site": 'same-origin',
                        "user-agent": 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
                        "x-app-version": '20241129.1',
                        "x-client-locale": 'en_US',
                        "x-client-platform": 'web',
                        "x-client-version": '1.2.0-sse-hint'
                    }
                })
                .then(res => res.json())
                .catch(err => ({ error: err.message }));
            """, session_id)

            if 'error' in response:
                print(f"Error fetching messages for session {session_id}: {response['error']}")
                # If existing entry exists but failed to fetch new data, use existing
                if existing_entry:
                    session_data_entries.append(existing_entry)
                    print(f"Using existing data for session {idx+1}/{session_summary_entries_len} (ID: {session_id}) due to fetch error.")
                continue

            session_data = response.get('data', {}).get('biz_data', {})
            session_data_entries.append(session_data)
            print(f"Fetched session {idx+1}/{session_summary_entries_len} (ID: {session_id}).")

        # Save to file
        with open(output_path, "w") as f:
            json.dump(session_data_entries, f, indent=2)
        print(f"Data saved to {output_path} for {len(session_data_entries)} sessions.")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        if driver:
            driver.quit()
            print("Browser closed.")

if __name__ == "__main__":
    main()