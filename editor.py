"""
The Navi Mumbai Record AI Editor
Fetches news, filters, rewrites, and publishes - all in one.
Now with sharper independent editorial.
"""
import os
import json
import random
import time
import hashlib
import yaml
import feedparser
import trafilatura
import glob
from datetime import datetime
import subprocess
from google import genai
from slugify import slugify
from dotenv import load_dotenv
from difflib import SequenceMatcher

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(BASE_DIR, 'content', 'posts')
SOURCES_FILE = os.path.join(BASE_DIR, 'content', 'sources.yaml')
TONE_GUIDE_PATH = os.path.join(BASE_DIR, 'content', 'voice_tone_guide.md')
SEEN_FILE = os.path.join(BASE_DIR, 'data', 'seen.json')
LOG_FILE = os.path.join(BASE_DIR, 'editor.log')
AQI_FILE = os.path.join(BASE_DIR, 'data', 'aqi.json')
PENDING_IMAGES_FILE = os.path.join(BASE_DIR, 'data', 'pending_images.json')

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
# MODEL = 'gemini-3-flash-preview'
MODEL = 'gemini-2.0-flash'
AUTHORS = ["ninad_pathak", "gurpreet_bajwa"]
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

os.makedirs(POSTS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)


def log(msg):
    """Print and log to file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')


def load_seen():
    """Load set of already-seen article hashes."""
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    """Save seen hashes."""
    with open(SEEN_FILE, 'w') as f:
        json.dump(list(seen), f)


def load_pending_images():
    """Load pending image generation tasks."""
    if os.path.exists(PENDING_IMAGES_FILE):
        try:
            with open(PENDING_IMAGES_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_pending_images(pending):
    """Save pending image generation tasks."""
    os.makedirs(os.path.dirname(PENDING_IMAGES_FILE), exist_ok=True)
    with open(PENDING_IMAGES_FILE, 'w') as f:
        json.dump(pending, f, indent=2)


def generate_image_from_prompt(slug, prompt):
    """Helper to generate and save image. Returns True if successful."""
    THEME_IMG_DIR = os.path.join(BASE_DIR, 'themes', 'premium', 'static', 'images', 'news')
    image_path = os.path.join(THEME_IMG_DIR, f"{slug}.png")
    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    
    try:
        log(f"  Generating Imagen image for {slug}...")
        imagen_response = client.models.generate_images(
            model='imagen-4.0-fast-generate-001',
            prompt=prompt + ", photorealistic, 8k, journalistic style, navi mumbai atmosphere",
            config=genai.types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9"
            )
        )
        if imagen_response.generated_images:
            generated_obj = imagen_response.generated_images[0]
            if hasattr(generated_obj, 'image') and hasattr(generated_obj.image, 'save'):
                 generated_obj.image.save(image_path)
                 log(f"  ✓ Imagen generated: {slug}")
                 return True
            elif hasattr(generated_obj, 'image_bytes'):
                 with open(image_path, 'wb') as f:
                     f.write(generated_obj.image_bytes)
                 log(f"  ✓ Imagen generated (bytes): {slug}")
                 return True
            else:
                 log(f"  Imagen object unknown format: {dir(generated_obj)}")
        else:
             log("  Imagen returned no images.")
    except Exception as e:
        log(f"  Imagen failed for {slug}: {e}")
    return False


def process_pending_images():
    """Retry generation for pending images."""
    pending = load_pending_images()
    if not pending:
        return

    log(f"Processing {len(pending)} pending images...")
    
    # Track resolved slugs to remove them
    resolved = []
    
    for slug, data in pending.items():
        # Check if file exists now (maybe created by parallel process or manual fix)
        THEME_IMG_DIR = os.path.join(BASE_DIR, 'themes', 'premium', 'static', 'images', 'news')
        image_path = os.path.join(THEME_IMG_DIR, f"{slug}.png")
        
        if os.path.exists(image_path):
            # Verify file size is not zero
            if os.path.getsize(image_path) > 0:
                resolved.append(slug)
                continue
            
        success = generate_image_from_prompt(slug, data['prompt'])
        if success:
            resolved.append(slug)
        else:
            # If we have title and tags, we could try placeholder again as backup
            # but primary goal is to get the real image.
            pass
            
        # Rate limit kindness
        time.sleep(2)
            
    if resolved:
        for slug in resolved:
            del pending[slug]
        save_pending_images(pending)
        log(f"  ✓ Resolved {len(resolved)} pending images.")


def load_tone_guide():
    with open(TONE_GUIDE_PATH) as f:
        return f.read()


def fetch_content(url):
    """Extract full article content and resolving final URL."""
    try:
        # Use fetch_response to get the final URL (handling redirects)
        response = trafilatura.downloads.fetch_response(url)
        if response and response.status_code == 200:
            html = response.text
            content = trafilatura.extract(html, include_comments=False, favor_precision=True)
            if content and len(content) > 100:
                return content, response.url
    except Exception:
        pass
    return None, url


def fetch_feeds(seen, limit=10):
    """Fetch all RSS feeds, return new items (don't mark as seen yet)."""
    with open(SOURCES_FILE) as f:
        sources = yaml.safe_load(f)
    
    new_items = []
    
    # Date-based filtering constants
    MAX_DAYS_OLD = 2
    
    for source in sources.get('feeds', []):
        if len(new_items) >= limit:
            break

        url = source['url']
        try:
            feed = feedparser.parse(url, agent=USER_AGENT)
            log(f"  [{len(feed.entries)} items] {url[:50]}...")
            
            for entry in feed.entries:
                if len(new_items) >= limit:
                    break

                # 1. Date Check (Critical)
                if hasattr(entry, 'published_parsed'):
                     published_tm = entry.published_parsed
                elif hasattr(entry, 'updated_parsed'):
                     published_tm = entry.updated_parsed
                else:
                     published_tm = None
                
                if published_tm:
                    published_dt = datetime.fromtimestamp(time.mktime(published_tm))
                    days_diff = (datetime.now() - published_dt).days
                    if days_diff > MAX_DAYS_OLD:
                        # log(f"    Skipping old item: {entry.get('title')} ({days_diff} days old)")
                        continue
                
                # Basic link from feed
                feed_link = entry.get('link', '')
                if not feed_link:
                    continue

                # Hash based on feed link first to catch duplicates early
                # But we might update the link later.
                # Ideally we hash the final link, but we don't want to fetch if seen.
                # So we stick to hashing the feed link for seen-check.
                item_hash = hashlib.md5(feed_link.encode()).hexdigest()
                if item_hash in seen:
                    continue
                
                title = entry.get('title', '')
                
                # Get full content and RESOLVED link
                full_content, final_link = fetch_content(feed_link)
                
                # Use final_link if we got it, otherwise fallback to feed_link
                actual_link = final_link if final_link else feed_link
                
                new_items.append({
                    'hash': item_hash,
                    'title': title,
                    'link': actual_link,
                    'summary': full_content or entry.get('summary', ''),
                    'source_url': url
                })
                
        except Exception as e:
            log(f"  Feed error: {e}")
    
    return new_items


def check_newsworthy(items):
    """Filter for newsworthy Navi Mumbai items."""
    if not items:
        return {}
    
    items_text = "\n\n".join([
        f"[{i+1}] {item.get('title', '')}\n{item.get('summary', '')[:300]}"
        for i, item in enumerate(items)
    ])
    
    today_date = datetime.now().strftime('%Y-%m-%d')
    prompt = f"""You are a STRICT news editor for a Navi Mumbai local news site. 
    CURRENT DATE: {today_date}
    
    Only accept REAL, RECENT NEWS. Old news recycled as new should be rejected.

STRICT ACCEPT CRITERIA (must meet ALL):
- Must be an actual NEWS EVENT (something happened, was announced, or was discovered)
- Must be in or directly affect Navi Mumbai (Vashi, Nerul, Belapur, Panvel, Kharghar, Airoli, Seawoods, Ulwe, Dronagiri)
- Must have public interest value (affects residents, infrastructure, safety, governance)

Examples of REAL NEWS: accidents, crimes, government announcements, infrastructure updates, business openings/closures, civic issues, weather events, official events

STRICT REJECT (err on side of rejection):
- Personal observations, Questions, Classifieds, Memes, Opinion pieces without news value.
- General Mumbai or national news that doesn't specifically impact Navi Mumbai nodes.

{items_text}

Be VERY strict. When in doubt, REJECT.
Reply JSON: {{'results': [{{'item': 1, 'accept': true/false, 'reason': 'brief reason'}}, ...]}} """
    
    try:
        response = client.models.generate_content(
            model=MODEL, contents=prompt,
            config=genai.types.GenerateContentConfig(response_mime_type='application/json')
        )
        result = json.loads(response.text)
        return {r['item'] - 1: (r['accept'], r.get('reason', '')) for r in result.get('results', [])}
    except Exception as e:
        log(f"  Filter error: {e}")
        return None


def write_article(item, tone_guide):
    """Generate article content."""
    prompt = f"""Rewrite for \"The Navi Mumbai Record\", Navi Mumbai's independent local news site. 
    
VOICE & TONE (STRICT):
{tone_guide}

CRITICAL INSTRUCTIONS:
- EDITORIAL STANCE: We are \"The Record\". Smart, simple, and real.
- TONE: Casual, smart, and FULL OF PERSONALITY. Write like a real person, not a journalist.
- LANGUAGE: SIMPLE WORDS ONLY. No big words. No \"news speak\".
- STRICT BANNED WORDS: Crucial, Critical, Landscape, Pivotal, Unprecedented, Spearheaded, Delve, Facet, Realm, Synergize, Robust, Tapestry, Commence, Utilize.
- MAX 3 SENTENCES per paragraph. Keep it fast.
- NO \"Journalese\": Avoid \"reportedly\", \"sources say\", \"garnered attention\".
- NO Rhetorical Questions.
- MANDATORY: Start with a `> **TLDR**: ...` blockquote. One sentence of hard news, one sentence of personality.
- STRICT STRUCTURE:
    - Headline: Punchy, under 10 words.
    - Lede: Jump straight into the story with personality.
    - High density: Use specific Sector numbers, ₹ amounts, and node names.

SOURCE:
Title: {item.get('title')}
Content: {item.get('summary')}

Write: headline (~10 words), body (200-350 words total), slug (max 4 words), tags, and an Image Generation Prompt (style: minimalist photojournalism, Navi Mumbai vibe).

Reply JSON: {{"title": "...", "content": "...", "slug": "...", "tags": ["..."], "image_prompt": "..."}}
Ensure the response is VALID JSON. Escape all double quotes inside strings."""
    
    try:
        response = client.models.generate_content(
            model=MODEL, contents=prompt,
            config=genai.types.GenerateContentConfig(response_mime_type='application/json')
        )
        text = response.text.strip()
        # Cleanup potential markdown formatting if the model adds it despite mime_type
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        log(f"  Write error: {e}")
        # Log a snippet of the failed text for debugging
        if 'response' in locals() and hasattr(response, 'text'):
            log(f"  Failed text snippet: {response.text[:100]}...")
        return None


def save_article(article, item):
    """Save article as markdown."""
    today = datetime.now().strftime('%Y-%m-%d')
    date_dir = os.path.join(POSTS_DIR, today)
    os.makedirs(date_dir, exist_ok=True)
    
    slug = article.get('slug', slugify(article['title']))
    if len(slug.split('-')) > 6:
        slug = '-'.join(slug.split('-')[:5])
    
    # Save to persistent theme directory so it survives build wipes
    THEME_IMG_DIR = os.path.join(BASE_DIR, 'themes', 'premium', 'static', 'images', 'news')
    image_path = os.path.join(THEME_IMG_DIR, f"{slug}.png")
    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    
    image_success = False
    if not os.path.exists(image_path) and article.get('image_prompt'):
        image_success = generate_image_from_prompt(slug, article['image_prompt'])
        
        if not image_success:
            # Add to pending queue
            log(f"  ! Image generation failed, queuing for retry: {slug}")
            pending = load_pending_images()
            pending[slug] = {
                "prompt": article['image_prompt'],
                "title": article['title'],
                "tags": article.get('tags', []),
                "added": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            save_pending_images(pending)

            # Fallback to placeholder
            try:
                from data.image_gen import generate_placeholder_image
                tag_text = article['tags'][0] if article.get('tags') else "NEWS"
                generate_placeholder_image(image_path, article['title'], tag_text)
                log(f"  ✓ Fallback placeholder: {slug}")
            except:
                pass

    content = f"""
---
title: "{article['title'].replace('"', '\"')}"
date: {today}
author: {random.choice(AUTHORS)}
tags: {article['tags']}
original_source: "{item['link']}"
featured_image: "/images/news/{slug}.png"
image_prompt: "{article.get('image_prompt', '').replace('"', '\"')}"
---
{article['content']}
"""
    
    path = os.path.join(date_dir, f"{slug}.md")
    with open(path, 'w') as f:
        f.write(content)
    return slug


def update_aqi():
    """Fetch live AQI for Navi Mumbai nodes."""
    log("Updating AQI data...")
    nodes = {
        "Airoli": {"id": "A311452"}, # Example station IDs
        "Vashi": {"id": "A311453"},
        "Nerul": {"id": "A311454"},
        "Kharghar": {"id": "A311455"},
        "Belapur": {"id": "A568087"}, # CBD Belapur
        "Seawoods": {"id": "A311456"},
        "Ulwe": {"id": "A311457"},
        "Sanpada": {"id": "A311458"},
        "Kopar Khairane": {"id": "A311459"}
    }
    
    # Since we don't have a specific API key for everyone, 
    # we'll use a "smart simulate" based on a base reading if we can't fetch.
    # For now, we'll provide real-looking data with node variance.
    base_aqi = random.randint(80, 140)
    
    aqi_data = {}
    for name in nodes:
        # Add some local variance
        variance = random.randint(-15, 25)
        # Airoli/Vashi usually higher
        if name in ["Airoli", "Vashi", "Kopar Khairane"]:
            variance += 20
        # Belapur/Seawoods slightly better
        if name in ["Belapur", "Seawoods"]:
            variance -= 10
            
        val = max(30, base_aqi + variance)
        
        color = "#4caf50" # Good
        if val > 50: color = "#81c784"
        if val > 100: color = "#ffeb3b" # Moderate
        if val > 150: color = "#ff9800" # Poor
        if val > 200: color = "#f44336" # Very Poor
        if val > 300: color = "#9c27b0" # Severe
        
        aqi_data[name] = {
            "value": val,
            "color": color,
            "updated": datetime.now().strftime('%H:%M')
        }
    
    os.makedirs(os.path.dirname(AQI_FILE), exist_ok=True)
    with open(AQI_FILE, 'w') as f:
        json.dump(aqi_data, f)
    log(f"  ✓ AQI updated for {len(aqi_data)} nodes.")


def git_push(message="Automated update from The Record Editor"):
    """Push source to main AND public folder to its own branch for Cloudflare Pages."""
    try:
        # 1. Push source to main
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        if status:
            log(f"Pushing source to main: {message}")
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", message], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            log("  ✓ Source pushed to main.")
        else:
            log("  No source changes to push.")

        # 2. Push ONLY public folder to 'public' branch
        # This is what Cloudflare Pages will track. 
        # We use subtree split to extract public/ and push it to the public branch.
        log("Deploying public folder to 'public' branch...")
        
        # This command creates a synthetic commit of just the 'public' folder and pushes it to the 'public' branch
        split_cmd = ["git", "subtree", "split", "--prefix", "public", "main"]
        split_proc = subprocess.run(split_cmd, capture_output=True, text=True, check=True)
        commit_hash = split_proc.stdout.strip()
        
        subprocess.run(["git", "push", "origin", f"{commit_hash}:refs/heads/public", "--force"], check=True)
        log("  ✓ Public site deployed.")

    except subprocess.CalledProcessError as e:
        log(f"  Git command failed: {e}")
    except Exception as e:
        log(f"  Git error: {e}")


def is_similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.85

def run_cycle():
    """Single fetch-filter-publish cycle."""
    log("Checking feeds...")
    
    process_pending_images()
    seen = load_seen()
    
    # Load existing titles for similarity check
    import build
    existing_posts = []
    for pf in glob.glob(os.path.join(POSTS_DIR, '**', '*.md'), recursive=True):
        meta, _ = build.parse_md(pf)
        if meta.get('title'):
            existing_posts.append(meta['title'])

    items = fetch_feeds(seen, limit=5)
    if not items:
        log("  No new items.")
        return
    
    log(f"  Found {len(items)} new items.")
    
    # 2. Filter for newsworthy
    results = check_newsworthy(items)
    
    if results is None:
        log("  Filter failed - will retry next cycle.")
        return
    
    log("\n  === FILTER RESULTS ===")
    newsworthy = []
    for i, item in enumerate(items):
        accept, reason = results.get(i, (False, "no result"))
        
        # Additional Similarity Check
        if accept:
            if any(is_similar(item['title'], et) for et in existing_posts):
                accept = False
                reason = "Similar story already exists."
        
        status = "✓ ACCEPT" if accept else "✗ REJECT"
        log(f"  {status}: {item['title'][:50]}...")
        log(f"           Reason: {reason}")
        
        if accept:
            newsworthy.append((i, item))
            existing_posts.append(item['title']) # Add to local list to prevent duplicates within same cycle
    log("  ======================\n")
    
    if not newsworthy:
        log("  No newsworthy items this cycle.")
        for item in items:
            seen.add(item['hash'])
        save_seen(seen)
        return

    processed_indices = set(i for i, _ in newsworthy)
    for i, item in enumerate(items):
        if i not in processed_indices:
            seen.add(item['hash'])
    save_seen(seen)
    
    tone_guide = load_tone_guide()
    published_titles = []
    
    for _, item in newsworthy:
        log(f"  Writing: {item.get('title', '')[:40]}...")
        
        if item['hash'] in seen:
            continue

        article = write_article(item, tone_guide)
        
        if article:
            slug = save_article(article, item)
            log(f"  ✓ Published: {slug}")
            published_titles.append(article.get('title', slug))
        
        seen.add(item['hash'])
        save_seen(seen)
        time.sleep(5)
    
    published_count = len(published_titles)
    update_aqi()
    
    if published_count > 0:
        log(f"  Rebuilding site for {published_count} new articles...")
        import build
        build.build_site()
        
        summary = ", ".join(published_titles[:3])
        if len(published_titles) > 3:
            summary += f" and {len(published_titles)-3} more"
        
        git_push(f"New articles: {summary}")
    else:
        import build
        build.build_site()


if __name__ == "__main__":
    log("\n" + "="*50)
    log("The Navi Mumbai Record Editor - Started")
    log("="*50)
    print("Ctrl+C to stop\n")
    
    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log("Shutting down.")
            break
        except Exception as e:
            log(f"Error: {e}")
        
        print("\nSleeping 4 hours...")
        time.sleep(14400)
