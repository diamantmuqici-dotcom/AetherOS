#!/usr/bin/env python3
"""Safe Site check — warns on phishing, doxxing, darkweb (.onion), and untrusted."""
import re
PHISH_PATTERNS = [
    r"secure[-.]login", r"verify[-.]account", r"free[-.]money", r"crypto[-.]airdrop",
    r"signin-[a-z0-9]+\.", r"apple-id-[a-z0-9]+\.", r"paypal-[a-z0-9]+\.",
]
DARKWEB = r"\.onion$"
DOXXING_HINTS = ["doxbin", "pastebin.com/raw", "familyrelatives", "homeaddress"]

def check(url: str) -> dict:
    u = url.lower()
    if ".onion" in u:
        return {"level": "darkweb", "msg": "Tor .onion — not recommended on this browser. Use Tor Browser."}
    for pat in PHISH_PATTERNS:
        if re.search(pat, u):
            return {"level": "phishing", "msg": "Possible phishing — domain looks similar to a trusted brand."}
    if any(h in u for h in DOXXING_HINTS):
        return {"level": "doxxing", "msg": "This site hosts personal/doxxing data. Blocked content warning."}
    # Gmail/Outlook are trusted as official domains only
    if "mail.google.com" in u or "outlook.office.com" in u:
        return {"level": "trusted", "msg": "Official mail domain."}
    return {"level": "ok", "msg": "No known phishing/doxxing pattern."}
