# DeepSeek Chat Exporter

Scrape DeepSeek chat history and save it to a JSON file. 

## Usage

1. `pip install -r requirements.txt`
2. `./installChromeDriver.sh`
3. `python main.py -o <path to destination file>`
   - You will need to log in manually (subsequent runs of the script will use the existing login session).
   - Will not work on VPN due to Cloudflare protection.
   - If the destination file exists, existing data will be merged with new data.