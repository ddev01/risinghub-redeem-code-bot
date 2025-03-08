# RisingHub Code Redemption Bot

This tool automates the process of redeeming promotional codes on RisingHub across multiple accounts and heroes.

## Features

- **Multi-Account Support**: Process multiple accounts sequentially with appropriate rate limiting
- **Smart Code Tracking**: Remember which codes have been attempted on which heroes to avoid redundant attempts
- **Prioritized Redemption**: Choose heroes based on configurable priorities (faction preference)
- **Session Management**: Persist login sessions using cookies to minimize authentication requests
- **Comprehensive Logging**: Track successful redemptions, failures, and informational events

## Setup

1. Install Python 3.8 or later
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create your configuration file:
   - A template `accounts.json` will be created on first run
   - Edit the template with your account information

## Configuration

Edit the `accounts.json` file with your account information:

```json
{
	"accounts": [
		{
			"username": "your_username",
			"password": "your_password",
			"priority_nat_hero": "yournatgunner",
			"priority_roy_hero": "yourroygunner",
			"priority_faction": "nat",
			"heroes": {}
		}
	],
	"settings": {
		"rate_limit_delay": 2.0,
		"codes_file": "redemption_codes.txt"
	}
}
```

## Redemption Codes

Add redemption codes to the `redemption_codes.txt` file (or whatever file you specify in `settings.codes_file`):

```
CODE1-ABCD-XYZ
CODE2-EFGH-XYZ
# This is a comment
CODE3-IJKL-XYZ # Inline comment
```

## Usage

Run the bot with:

```
python main.py
```

## Output Files

- **Session Cookies**: Stored in `sessions/{username}/session_cookies.json`
- **Redemption Logs**:
  - `logs/{username}/{username}_redemption_success.csv`: Successful redemptions
  - `logs/{username}/{username}_redemption_failure.csv`: Failed redemptions
  - `logs/{username}/{username}_redemption_info.csv`: Informational responses
  - `logs/redeemed_codes.csv`: Master record of all redemption attempts

## How It Works

1. The bot loads account configurations and redemption codes.
2. For each account, it loads stored hero information.
3. It filters out codes that have already been redeemed by all heroes.
4. It authenticates and retrieves current hero information.
5. It tries to redeem remaining codes, prioritizing heroes based on your settings.
6. All redemption attempts are tracked for future reference.

The system intelligently avoids redundant attempts by checking if codes have already been tried on specific heroes, improving efficiency for repeat runs.

## License

This project is licensed for personal use only. Do not use this for commercial purposes. 