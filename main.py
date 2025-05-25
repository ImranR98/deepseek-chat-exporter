import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import json
import getpass
import os
import time

def main():
    driver = None
    try:
        # Prep Chromium
        options = uc.ChromeOptions()
        dataDir = f"/home/{getpass.getuser()}/.config/chromium"
        if not os.path.isdir(dataDir):
            dataDir = f"/home/{getpass.getuser()}/.config/google-chrome"
        if os.path.isdir(dataDir):
            options.add_argument(f"--profile-directory=Default")
        driver = uc.Chrome(options=options,user_data_dir=dataDir)

        # Wait for manual login
        driver.get("https://chat.deepseek.com")
        WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((uc.By.CSS_SELECTOR, "#chat-input"))
        )

        # Grab all chat session IDs
        session_summary_entries = []
        has_more = True
        params = None
        while has_more:
            response = driver.execute_script("""
                const params = arguments[0];
                let url = '/api/v0/chat_session/fetch_page';
                if (params) {
                    url += '?' + new URLSearchParams(params).toString();
                }
                return fetch(url, {
                    method: 'GET',
                    credentials: 'include',
                    headers: {
                        Authorization: 'Bearer ' + JSON.parse(localStorage.getItem('userToken')).value
                    }
                })
                .then(res => res.json())
                .catch(err => ({ error: err.message }));
            """, params)

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
        print(f"Found {session_summary_entries_len} chat sessions. Fetching messages...")

        # Grab session data
        session_data_entries = []
        for idx, session in enumerate(session_summary_entries):
            session_id = session.get('id')
            if not session_id:
                continue

            response = driver.execute_script("""
                const sessionId = arguments[0];
                return fetch(`/api/v0/chat/history_messages?chat_session_id=${sessionId}`, {
                    method: 'GET',
                    credentials: 'include',
                    headers: {
                        Authorization: 'Bearer ' + JSON.parse(localStorage.getItem('userToken')).value
                    }
                })
                .then(res => res.json())
                .catch(err => ({ error: err.message }));
            """, session_id)

            if 'error' in response:
                print(f"Error fetching messages for session {session_id}: {response['error']}")
                continue

            session_data_entries.append(response.get('data', {}).get('biz_data', {}))
            
            print(f"Saved session {idx+1}/{session_summary_entries_len}")
        
        # Save to file
        with open("chat_data.json", "w") as f:
            json.dump(session_data_entries, f, indent=2)
        print(f"Data saved for {session_summary_entries_len} sessions")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        if driver:
            driver.quit()
            print("Browser closed.")

if __name__ == "__main__":
    main()