"""
Static Site Generator for The Flamingo
Simple, fast, no dependencies beyond jinja2/markdown/pyyaml
"""
import os
import shutil
import glob
import yaml
import markdown
import jinja2
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENT_DIR = os.path.join(BASE_DIR, 'content')
THEME_DIR = os.path.join(BASE_DIR, 'themes', 'premium')
PUBLIC_DIR = os.path.join(BASE_DIR, 'public')

# Jinja setup
env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.join(THEME_DIR, 'templates')))


def parse_md(filepath):
    """Parse markdown file with YAML frontmatter."""
    with open(filepath) as f:
        text = f.read()
    
    if text.startswith('---'):
        parts = text.split('---', 2)
        if len(parts) >= 3:
            try:
                meta = yaml.safe_load(parts[1])
            except yaml.YAMLError:
                meta = {}
            return meta or {}, markdown.markdown(parts[2])
    return {}, markdown.markdown(text)


def build_site():
    print(f"Building site...")
    
    # Clear news directory
    news_dir = os.path.join(PUBLIC_DIR, 'news')
    if os.path.exists(news_dir):
        shutil.rmtree(news_dir)
    
    # Load config
    with open(os.path.join(CONTENT_DIR, 'config.yaml')) as f:
        config = yaml.safe_load(f)
    
    # Load authors
    authors = {}
    for af in glob.glob(os.path.join(CONTENT_DIR, 'authors', '*.md')):
        slug = os.path.basename(af).replace('.md', '')
        meta, bio = parse_md(af)
        authors[slug] = {**meta, 'bio_html': bio, 'slug': slug}
    
    # Load posts
    posts = []
    for pf in glob.glob(os.path.join(CONTENT_DIR, 'posts', '**', '*.md'), recursive=True):
        meta, content = parse_md(pf)
        slug = os.path.basename(pf).replace('.md', '')
        date = str(meta.get('date', datetime.now().strftime('%Y-%m-%d')))
        
        posts.append({
            **meta,
            'content': content,
            'slug': slug,
            'url': f"/news/{date}/{slug}.html",
            'author_details': authors.get(meta.get('author', 'ai_bot'), {})
        })
    
    # Load AQI data
    aqi_data = {}
    aqi_path = os.path.join(BASE_DIR, 'data', 'aqi.json')
    if os.path.exists(aqi_path):
        with open(aqi_path) as f:
            aqi_data = yaml.safe_load(f)

    # Load Ads data
    ads_data = {}
    ads_path = os.path.join(CONTENT_DIR, 'ads.yaml')
    if os.path.exists(ads_path):
        with open(ads_path) as f:
            ads_data = yaml.safe_load(f)

    # Update config with dynamic data
    config['aqi'] = aqi_data
    config['ads'] = ads_data
    
    # Sort posts by date descending
    posts.sort(key=lambda x: str(x.get('date', '')), reverse=True)
    
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    
    # Render index
    output = env.get_template('index.html').render(site=config, latest_news=posts[:10], title=config['site_name'])
    with open(os.path.join(PUBLIC_DIR, 'index.html'), 'w') as f:
        f.write(output)
    
    # Render archive
    output = env.get_template('archive.html').render(site=config, posts=posts, title="Archives")
    with open(os.path.join(PUBLIC_DIR, 'archive.html'), 'w') as f:
        f.write(output)

    # Render AQI Map
    if os.path.exists(os.path.join(THEME_DIR, 'templates', 'aqi.html')):
        output = env.get_template('aqi.html').render(site=config, title="AQI Map")
        with open(os.path.join(PUBLIC_DIR, 'aqi.html'), 'w') as f:
            f.write(output)
    
    # Render authors list
    output = env.get_template('authors.html').render(site=config, authors=authors, title="Our Journalists")
    with open(os.path.join(PUBLIC_DIR, 'authors.html'), 'w') as f:
        f.write(output)

    # Render generic pages
    page_tpl = env.get_template('page.html')
    for pf in glob.glob(os.path.join(CONTENT_DIR, '*.md')):
        # Skip files that are not supposed to be pages
        if os.path.basename(pf) == 'voice_tone_guide.md':
            continue
            
        slug = os.path.basename(pf).replace('.md', '')
        meta, content = parse_md(pf)
        output = page_tpl.render(site=config, content=content, title=meta.get('title', slug), subtitle=meta.get('subtitle', ''))
        with open(os.path.join(PUBLIC_DIR, f"{slug}.html"), 'w') as f:
            f.write(output)
    
    # Render articles
    article_tpl = env.get_template('article.html')
    for post in posts:
        date = str(post.get('date', datetime.now().strftime('%Y-%m-%d')))
        out_dir = os.path.join(PUBLIC_DIR, 'news', date)
        os.makedirs(out_dir, exist_ok=True)
        
        output = article_tpl.render(site=config, post=post, title=post.get('title'))
        with open(os.path.join(out_dir, f"{post['slug']}.html"), 'w') as f:
            f.write(output)
    
    # Render author pages
    author_tpl = env.get_template('author.html')
    os.makedirs(os.path.join(PUBLIC_DIR, 'author'), exist_ok=True)
    for slug, author in authors.items():
        author_posts = [p for p in posts if p.get('author') == slug]
        output = author_tpl.render(site=config, author=author, posts=author_posts, title=author.get('name'))
        with open(os.path.join(PUBLIC_DIR, 'author', f"{slug}.html"), 'w') as f:
            f.write(output)
    
    # Generate RSS Feed
    rss_items = []
    for post in posts[:20]:
        rss_items.append(f"""        <item>
            <title>{post.get('title')}</title>
            <link>{config.get('site_url')}{post.get('url')}</link>
            <description>{post.get('content')[:500]}...</description>
            <pubDate>{post.get('date')}</pubDate>
            <guid>{config.get('site_url')}{post.get('url')}</guid>
        </item>""")
    
    rss_xml = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
    <channel>
        <title>{config.get('site_name')}</title>
        <link>{config.get('site_url')}</link>
        <description>{config.get('site_description')}</description>
{chr(10).join(rss_items)}
    </channel>
</rss>"""
    with open(os.path.join(PUBLIC_DIR, 'rss.xml'), 'w') as f:
        f.write(rss_xml)

    # Copy CSS
    os.makedirs(os.path.join(PUBLIC_DIR, 'css'), exist_ok=True)
    src_css = os.path.join(THEME_DIR, 'static', 'css', 'style.css')
    if os.path.exists(src_css):
        shutil.copy(src_css, os.path.join(PUBLIC_DIR, 'css', 'style.css'))
    
    # Copy Images
    src_imgs = os.path.join(THEME_DIR, 'static', 'images')
    dst_imgs = os.path.join(PUBLIC_DIR, 'images')
    if os.path.exists(src_imgs):
        if os.path.exists(dst_imgs):
            shutil.rmtree(dst_imgs)
        shutil.copytree(src_imgs, dst_imgs)
    
    print(f"Built {len(posts)} articles.")


if __name__ == "__main__":
    build_site()
