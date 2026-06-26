#!/usr/bin/env python3
"""
LeadGen — Fake Site Viewer
Opens fake-site leads one by one in your browser so you can see what they look like.
Usage: python view_fake_sites.py [good_leads_csv]
"""

import csv
import sys
import glob
import os
import webbrowser
import time
from collections import defaultdict

R  = "\033[91m"; G  = "\033[92m"; Y  = "\033[93m"; B  = "\033[94m"
M  = "\033[95m"; C  = "\033[96m"; W  = "\033[97m"; DIM= "\033[2m"
BLD= "\033[1m";  RST= "\033[0m"

def red(s):     return f"{R}{s}{RST}"
def green(s):   return f"{G}{s}{RST}"
def yellow(s):  return f"{Y}{s}{RST}"
def cyan(s):    return f"{C}{s}{RST}"
def white(s):   return f"{W}{s}{RST}"
def bold(s):    return f"{BLD}{s}{RST}"
def dim(s):     return f"{DIM}{s}{RST}"

def resolve_path():
    if len(sys.argv) >= 2:
        return sys.argv[1]
    files = sorted([f for f in glob.glob("good_leads_2*.csv")
                    if 'highvalue' not in f and 'nowebsite' not in f], reverse=True)
    if files:
        return files[0]
    triaged = sorted(glob.glob("florida_triaged_*.csv"), reverse=True)
    if triaged:
        return triaged[0]
    print(red("No good_leads_*.csv or florida_triaged_*.csv found."))
    sys.exit(1)

def main():
    path = resolve_path()

    with open(path, newline='', encoding='utf-8') as f:
        leads = list(csv.DictReader(f))

    # Pull fake sites — works whether lead_tier or url_type column is present
    fake = []
    for l in leads:
        tier     = l.get('lead_tier', '')
        url_type = l.get('url_type', '')
        if tier == 'fake_website' or url_type == 'fake':
            fake.append(l)

    if not fake:
        print(red("No fake-site leads found in this file."))
        sys.exit(1)

    # Sort by review count descending so you see the most established first
    fake.sort(key=lambda x: int(x.get('review_count') or 0), reverse=True)

    print()
    print('═'*70)
    print(f"  {bold(cyan('LeadGen — Fake Site Viewer'))}")
    print('═'*70)
    print(f"  {dim('File: '+path)}")
    print(f"  {bold(yellow(str(len(fake))))} fake-site leads found")
    print()

    # Summary by platform
    platform_counts = defaultdict(int)
    for l in fake:
        url = (l.get('final_url') or l.get('website') or '').lower()
        if 'facebook'    in url: platform_counts['Facebook'] += 1
        elif 'wix'       in url: platform_counts['Wix'] += 1
        elif 'instagram' in url: platform_counts['Instagram'] += 1
        elif 'yelp'      in url: platform_counts['Yelp'] += 1
        elif 'linkedin'  in url: platform_counts['LinkedIn'] += 1
        elif 'canva'     in url: platform_counts['Canva'] += 1
        elif 'wordpress' in url: platform_counts['WordPress.com'] += 1
        elif 'squarespace' in url: platform_counts['Squarespace'] += 1
        elif 'sites.google' in url: platform_counts['Google Sites'] += 1
        else:                    platform_counts['Other'] += 1

    print(f"  {bold('Platform breakdown:')}")
    max_p = max(platform_counts.values())
    for platform, count in sorted(platform_counts.items(), key=lambda x: -x[1]):
        filled = round((count/max_p)*25)
        b = f"{Y}{'█'*filled}{DIM}{'░'*(25-filled)}{RST}"
        print(f"    {yellow(platform.ljust(18))} {b} {bold(str(count))}")
    print()

    # Filter options
    print(f"  Filter by platform (or press Enter to see all):")
    platforms = sorted(platform_counts.keys())
    for i, p in enumerate(platforms, 1):
        print(f"    {dim(str(i)+'.')} {p} {dim('('+str(platform_counts[p])+')')}")
    print(f"    {dim(str(len(platforms)+1)+'.')} All platforms")
    print()

    choice = input("  Choice [Enter = all]: ").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(platforms):
            selected = platforms[idx].lower()
            fake = [l for l in fake if selected in (l.get('final_url') or l.get('website') or '').lower()]
            print(f"  {green('→')} Filtered to {bold(platforms[idx])}: {len(fake)} leads")
        # else: all
    print()

    # Sort option
    print(f"  Sort by:")
    print(f"    {dim('1.')} Review count (default)")
    print(f"    {dim('2.')} City")
    print(f"    {dim('3.')} Industry")
    sort_choice = input("  Choice [Enter = reviews]: ").strip()
    if sort_choice == '2':
        fake.sort(key=lambda x: x.get('city',''))
    elif sort_choice == '3':
        fake.sort(key=lambda x: x.get('industry',''))
    else:
        fake.sort(key=lambda x: int(x.get('review_count') or 0), reverse=True)
    print()

    # Main viewer loop
    print('═'*70)
    print(f"  {bold('VIEWER')}  —  {len(fake)} leads")
    print(f"  {dim('Commands: Enter=open+next  s=skip  b=back  q=quit  g=go to #')}")
    print('═'*70)
    print()

    i = 0
    while 0 <= i < len(fake):
        l       = fake[i]
        name    = l.get('name', 'Unknown')
        city    = l.get('city', '')
        ind     = l.get('industry', '')
        reviews = int(l.get('review_count') or 0)
        rating  = l.get('rating', '')
        url     = l.get('final_url') or l.get('website') or ''
        phone   = l.get('phone', '')

        # Detect platform
        url_lower = url.lower()
        if 'facebook'    in url_lower: platform = 'Facebook'
        elif 'wix'       in url_lower: platform = 'Wix'
        elif 'instagram' in url_lower: platform = 'Instagram'
        elif 'yelp'      in url_lower: platform = 'Yelp'
        elif 'linkedin'  in url_lower: platform = 'LinkedIn'
        elif 'canva'     in url_lower: platform = 'Canva'
        elif 'wordpress' in url_lower: platform = 'WordPress.com'
        elif 'squarespace' in url_lower: platform = 'Squarespace'
        elif 'sites.google' in url_lower: platform = 'Google Sites'
        else:                          platform = 'Other'

        print(f"  {dim('['+str(i+1)+'/'+str(len(fake))+']')}  {bold(white(name))}")
        print(f"  {dim('City:')     } {city}  {dim('|')}  {dim('Industry:')} {ind}")
        print(f"  {dim('Reviews:')  } {yellow(str(reviews)+'★')}  {dim('|')}  {dim('Rating:')} {green(str(rating))}  {dim('|')}  {dim('Phone:')} {phone}")
        print(f"  {dim('Platform:') } {yellow(bold(platform))}")
        print(f"  {dim('URL:')      } {cyan(url)}")
        print()
        print(f"  {dim('[Enter]')} open in browser + next   {dim('[s]')} skip   {dim('[b]')} back   {dim('[q]')} quit   {dim('[g]')} go to #")

        cmd = input("  > ").strip().lower()
        print()

        if cmd == 'q':
            break
        elif cmd == 'b':
            i = max(0, i-1)
            continue
        elif cmd == 's':
            i += 1
            continue
        elif cmd.startswith('g'):
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit():
                target = int(parts[1]) - 1
                if 0 <= target < len(fake):
                    i = target
                else:
                    print(f"  {red('Out of range.')}")
            else:
                num = input("  Go to #: ").strip()
                if num.isdigit():
                    i = max(0, min(int(num)-1, len(fake)-1))
            continue
        else:
            # Enter or anything else = open + advance
            if url:
                webbrowser.open(url)
                time.sleep(0.3)  # slight delay so browser tab opens cleanly
            else:
                print(f"  {red('No URL for this lead.')}")
            i += 1

    print()
    print('═'*70)
    print(f"  {bold(cyan('Done.'))}  Viewed {i} of {len(fake)} fake-site leads.")
    print('═'*70)
    print()

if __name__ == '__main__':
    main()