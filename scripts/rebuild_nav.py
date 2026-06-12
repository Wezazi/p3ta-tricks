#!/usr/bin/env python3
"""Rebuild htb-academy nav with 13 topic groups for academy cheat sheets."""
import json
from pathlib import Path

ROOT    = Path(__file__).parent.parent
NAV_DIR = ROOT / "content" / "nav"

# ── Classification map ─────────────────────────────────────────────────────────
# Maps title (exact) → group name
TITLE_TO_GROUP = {
    # Active Directory
    "Active Directory BloodHound":          "Active Directory",
    "Active Directory Enumeration":         "Active Directory",
    "Active Directory Enumeration & Attacks": "Active Directory",
    "Active Directory LDAP":                "Active Directory",
    "Active Directory PowerView":           "Active Directory",
    "Active Directory Trust Attacks":       "Active Directory",
    "DACL Attacks I":                       "Active Directory",
    "DACL Attacks II":                      "Active Directory",
    "Introduction to Active Directory":     "Active Directory",
    "Kerberos Attacks":                     "Active Directory",
    "MSSQL, Exchange, and SCCM Attacks":    "Active Directory",
    "NTLM Relay Attacks CheatSheet":        "Active Directory",
    "Windows Attacks & Defense":            "Active Directory",
    "Windows Lateral Movement":             "Active Directory",
    "Detecting Access Token Manipulation Attacks": "Active Directory",

    # Windows
    "Evil-WinRM RUNas System":              "Windows",
    "Introduction to Windows Command Line": "Windows",
    "Introduction to Windows Evasion Techniques": "Windows",
    "Windows Fundamentals":                 "Windows",
    "Stack-Based Buffer Overflows on Windows x86": "Windows",
    "Process Injection Attacks and Detection": "Windows",

    # Linux
    "Linux Fundamentals":                   "Linux",
    "MacOS Fundamentals":                   "Linux",

    # Web Attacks
    "Abusing HTTP Misconfigurations":       "Web Attacks",
    "Advanced Deserializations Attacks":    "Web Attacks",
    "Advanced SQL Injections":              "Web Attacks",
    "Advanced XSS and CSRF Exploitation":   "Web Attacks",
    "Attacking Authentication Mechanisms":  "Web Attacks",
    "Attacking Common Applications":        "Web Attacks",
    "Attacking Common Services":            "Web Attacks",
    "Attacking GraphQL":                    "Web Attacks",
    "Blind SQL Injection":                  "Web Attacks",
    "Broken Authentication":                "Web Attacks",
    "Command Injections":                   "Web Attacks",
    "Cross-Site Scripting (XSS)":           "Web Attacks",
    "File Inclusion":                       "Web Attacks",
    "File Upload Attacks":                  "Web Attacks",
    "HTTP Attacks":                         "Web Attacks",
    "HTTPsTLS Attacks":                     "Web Attacks",
    "Hacking WordPress":                    "Web Attacks",
    "Injection Attacks":                    "Web Attacks",
    "Introduction to Deserialization Attacks": "Web Attacks",
    "Introduction to NoSQL Injection":      "Web Attacks",
    "JavaScript Deobfuscation":             "Web Attacks",
    "Login Brute Forcing":                  "Web Attacks",
    "SQL Injection Fundamentals":           "Web Attacks",
    "SQLMap Essentials":                    "Web Attacks",
    "SQLmap":                               "Web Attacks",
    "Secure Coding 101_ JavaScript":        "Web Attacks",
    "Server-side Attacks":                  "Web Attacks",
    "Using Web Proxies":                    "Web Attacks",
    "Web Attacks":                          "Web Attacks",
    "Web Proxies":                          "Web Attacks",
    "Web Requests":                         "Web Attacks",
    "Whitebox Attacks":                     "Web Attacks",
    "Whitebox Pentesting 101 Command Injection": "Web Attacks",
    "Whitebox Pentesting 101_ Command Injection": "Web Attacks",
    "XSS":                                  "Web Attacks",

    # Enumeration
    "Attacking Web Applications with Ffuf": "Enumeration",
    "FFUF":                                 "Enumeration",
    "Footprinting":                         "Enumeration",
    "Information Gathering":                "Enumeration",
    "Information Gathering - Web Edition":  "Enumeration",
    "Network Enumeration Cheat Sheet":      "Enumeration",
    "Web Fuzzing":                          "Enumeration",

    # Password Attacks
    "Cracking Passwords with Hashcat":      "Password Attacks",
    "Password Attacks":                     "Password Attacks",

    # Pivoting & Tunneling
    "Pivoting":                             "Pivoting & Tunneling",
    "Pivoting, Tunneling, and Port Forwarding": "Pivoting & Tunneling",
    "Metasploit":                           "Pivoting & Tunneling",

    # File Transfers
    "File Transfers":                       "File Transfers",

    # Wireless
    "Attacking WPAWPA2 Wi-Fi Networks":     "Wireless",
    "Attacking WPA_WPA2 Wi-Fi Networks":    "Wireless",
    "Attacking Wi-Fi Protected Setup (WPS)":"Wireless",
    "Wi-Fi Evil Twin Attacks":              "Wireless",
    "Wi-Fi Penetration Testing Basics":     "Wireless",
    "Wired Equivalent Privacy (WEP) Attacks": "Wireless",

    # Android & Mobile
    "Android Fundamentals":                 "Android & Mobile",
    "Andriod Fundamentals":                 "Android & Mobile",

    # Exploitation
    "Assembly Language":                    "Exploitation",
    "Game Hacking Fundamentals":            "Exploitation",
    "Intro to Assembly Language":           "Exploitation",
    "Intro to C2 Operations with Sliver":   "Exploitation",
    "Intro to Whitebox Pentesting":         "Exploitation",
    "Introduction to C":                    "Exploitation",
    "Introduction to C#":                   "Exploitation",
    "Shells & Payloads":                    "Exploitation",
    "Supply Chain Attacks":                 "Exploitation",

    # Forensics & Malware
    "Malicious Document Analysis":          "Forensics & Malware",
    "Network Traffic Analysis":             "Forensics & Malware",
    "User Behavior Forensics":              "Forensics & Malware",

    # Getting Started
    "Basic Commands":                       "Getting Started",
    "Getting Started":                      "Getting Started",
    "Pentest in a Nutshell":                "Getting Started",
    "Tools of the Trade":                   "Getting Started",
    "Using CrackMapExec":                   "Getting Started",

    # NVIM
    "NVIM Basics":                          "NVIM",
    "NVIM Advanced":                        "NVIM",
}

GROUP_ORDER = [
    "Active Directory",
    "Windows",
    "Linux",
    "Web Attacks",
    "Enumeration",
    "Password Attacks",
    "Pivoting & Tunneling",
    "File Transfers",
    "Wireless",
    "Android & Mobile",
    "Exploitation",
    "Forensics & Malware",
    "Getting Started",
    "NVIM",
    "Other",
]


def rebuild():
    nav_path = NAV_DIR / "cheatsheet.json"
    nav = json.loads(nav_path.read_text())

    # Extract academy cheat sheets section
    academy_items = []
    other_sections = []
    for section in nav:
        if section.get("title") == "Cheat Sheets":
            academy_items = section["items"]
        else:
            other_sections.append(section)

    # Classify each item into a group
    groups: dict[str, list] = {g: [] for g in GROUP_ORDER}
    unclassified = []
    for item in academy_items:
        title = item["title"]
        group = TITLE_TO_GROUP.get(title)
        if group:
            groups[group].append(item)
        else:
            unclassified.append(item)
            print(f"  UNCLASSIFIED: {title}")

    if unclassified:
        groups["Other"].extend(unclassified)

    # Build new nav: grouped academy sections first, then reference sections
    new_nav = []
    for group_name in GROUP_ORDER:
        items = sorted(groups[group_name], key=lambda x: x["title"])
        if items:
            new_nav.append({"type": "section", "title": group_name, "items": items})

    # Prefix all reference sections to distinguish from academy topic groups
    for sec in other_sections:
        sec = dict(sec, title=f"Reference — {sec['title']}")
        new_nav.append(sec)

    nav_path.write_text(json.dumps(new_nav, ensure_ascii=False, indent=2))
    print(f"\nNav rebuilt: {sum(len(g) for g in groups.values())} items in {len([g for g in groups.values() if g])} groups")
    for g in GROUP_ORDER:
        if groups[g]:
            print(f"  {g}: {len(groups[g])}")


if __name__ == "__main__":
    rebuild()
