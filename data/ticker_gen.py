def update_ticker(posts):
    """Generate ticker content only from real recent articles."""
    if not posts:
        return [
            "THE RECORD: QUIET DAY IN NAVI MUMBAI",
            "AWAITING SIGNAL FROM THE NODES",
            "SEND LEADS TO LEADS@NAVIMUMBAIRECORD.COM"
        ]
    
    ticker_items = []
    
    # Take up to 5 latest headlines
    for p in posts[:5]:
        # Convert title to uppercase for ticker style
        title = p.get('title', '').upper()
        # Clean up any potential markdown or extra chars
        title = title.replace('*', '').replace('"', '').strip()
        ticker_items.append(title)
        
    return ticker_items
