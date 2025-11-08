import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import arxiv
import feedparser
from flask import send_from_directory
# --- Database Configuration ---

# Get the absolute path of the directory where this file is located
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)

# Tell Flask where to find our database file
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'secufeed.db')
# Suppress a deprecation warning
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize the database extension
db = SQLAlchemy(app)

# Define pagination settings
PER_PAGE = 10
# --- Database Model Definition ---

# We define a class that represents the 'interests' table in our database.
# Each instance of this class will be a row in the table.

class Interest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keyword = db.Column(db.String(100), nullable=False)
    # Add this new column to store the type ('topic' or 'author')
    interest_type = db.Column(db.String(50), nullable=False, default='topic')

    def __repr__(self):
        return f'<Interest {self.keyword} ({self.interest_type})>'
    
class Bookmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.String(100), unique=True, nullable=False) # arXiv's unique ID
    title = db.Column(db.String(500), nullable=False)
    summary = db.Column(db.Text, nullable=False)
    authors = db.Column(db.String(500), nullable=False)
    pdf_link = db.Column(db.String(200), nullable=False)
    published_date = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f'<Bookmark {self.title}>'

# The search_for_papers function remains exactly the same
# In app.py

def search_for_papers(keyword, search_type, max_results=50):
    try:
        """
        Searches for papers on arXiv using a specific search type.
        """
        query = keyword.strip()
        
        # Use the search_type to build the correct query string
        if search_type == 'author':
            final_query = f'au:"{query}"'
        else: # Default to a general topic search
            final_query = query

        print(f"Executing arXiv search with query: '{final_query}'")

        search = arxiv.Search(
            query=final_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.LastUpdatedDate
        )

        found_papers = []
        for result in search.results():
            paper_info = {
                "entry_id": result.entry_id,
                "title": result.title,
                "summary": result.summary,
                "authors": [author.name for author in result.authors],
                "published_date": result.published.strftime("%Y-%m-%d"),
                "pdf_link": result.pdf_url,
                "topic": keyword
            }
            found_papers.append(paper_info)
        return found_papers
    except Exception as e:
        print(f"Error during arXiv search: {e}")
        return []
    
def fetch_rss_feeds():
    """Fetch articles from security RSS feeds"""
    feeds = [
        ('The Hacker News', 'http://feeds.feedburner.com/TheHackerNews'),
        ('Dark Reading', 'https://darkreading.com/rss.xml'),
        ('Security Week', 'https://securityweek.com/feed/')
    ]
    
    all_articles = []
    for source_name, feed_url in feeds:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:10]:
            # Normalize the data into a common format
            article = {
                'id': entry.get('id', entry.link), # Use link as a fallback ID
                'title': entry.title,
                'summary': entry.get('summary', 'No summary available.'),
                'link': entry.link,
                'published_date': entry.get('published', 'N/A'),
                'source': source_name,
                'type': 'news' # Add a type to distinguish from papers
            }
            all_articles.append(article)
    
    return all_articles

# --- Route Definitions ---

@app.route('/')
@app.route('/page/<int:page>')
def home(page=1):
    interests = Interest.query.all()
    all_papers = []
    for interest in interests:
        papers = search_for_papers(interest.keyword, interest.interest_type)
        all_papers.extend(papers)

    # --- New Deduplication Logic ---
    unique_papers = []
    seen_ids = set()
    for paper in all_papers:
        if paper['entry_id'] not in seen_ids:
            unique_papers.append(paper)
            seen_ids.add(paper['entry_id'])
    
    # Sort the unique papers by date
    unique_papers.sort(key=lambda x: x['published_date'], reverse=True)
    
    # --- New addition: Get a list of currently bookmarked paper IDs ---
    bookmarked_ids = {b.entry_id for b in Bookmark.query.all()}

    # --- Pagination Logic ---
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    
    # Get the slice of papers for the current page
    paginated_papers = unique_papers[start:end]
    # Calculate the total number of pages needed
    total_pages = (len(unique_papers) // PER_PAGE) + (len(unique_papers) % PER_PAGE > 0)
    
    return render_template('index.html',
                           papers=paginated_papers,
                           interests=interests,
                           current_page=page,
                           total_pages=total_pages,
                           bookmarked_ids=bookmarked_ids)



# This new route will handle adding new interests
# It accepts POST requests, which is how forms send data

@app.route('/add', methods=['POST'])
def add_interest():
    new_keyword = request.form.get('keyword')
    # Get the new interest type from the form's dropdown
    new_type = request.form.get('interest_type')
    
    if new_keyword and new_type:
        # Check if this exact keyword/type combo already exists
        existing = Interest.query.filter_by(keyword=new_keyword, interest_type=new_type).first()
        if not existing:
            # Create a new Interest object with the type
            interest = Interest(keyword=new_keyword, interest_type=new_type)
            db.session.add(interest)
            db.session.commit()
            
    return redirect(url_for('home'))

@app.route('/delete/<int:interest_id>')
def delete_interest(interest_id):
    # .get_or_404() is a handy function that either gets the object or returns a 404 Not Found error
    interest_to_delete = Interest.query.get_or_404(interest_id)
    
    # Remove the object from the database session
    db.session.delete(interest_to_delete)
    
    # Commit the change to the database
    db.session.commit()
    
    # Redirect the user back to the homepage
    return redirect(url_for('home'))

@app.route('/bookmarks')
def bookmarks():
    # Query the database for all saved bookmarks
    bookmarked_papers = Bookmark.query.order_by(Bookmark.published_date.desc()).all()
    return render_template('bookmarks.html', papers=bookmarked_papers)

@app.route('/toggle_bookmark', methods=['POST'])
def toggle_bookmark():
    # Get all the paper's data from the hidden form fields
    entry_id = request.form.get('entry_id')
    
    # Check if this paper is already bookmarked
    existing_bookmark = Bookmark.query.filter_by(entry_id=entry_id).first()

    if existing_bookmark:
        # If it exists, delete it (un-bookmark)
        db.session.delete(existing_bookmark)
        db.session.commit()
    else:
        # If it doesn't exist, create a new bookmark
        new_bookmark = Bookmark(
            entry_id=entry_id,
            title=request.form.get('title'),
            summary=request.form.get('summary'),
            authors=request.form.get('authors'),            
            pdf_link=request.form.get('pdf_link'),
            published_date=request.form.get('published_date')
        )
        db.session.add(new_bookmark)
        db.session.commit()
    
    # Redirect back to the page the user was on
    return redirect(request.referrer or url_for('home'))

# In app.py

@app.route('/search', methods=['GET', 'POST'])
def search():
    # If the user submitted the search form
    if request.method == 'POST':
        query = request.form.get('query')
        search_type = request.form.get('search_type')
        
        # Use our existing function to get the papers
        papers = search_for_papers(query, search_type, max_results=20)
        
        # We still need to know which papers are bookmarked to show the correct button state
        bookmarked_ids = {b.entry_id for b in Bookmark.query.all()}
        
        return render_template('search.html', papers=papers, query=query, bookmarked_ids=bookmarked_ids)

    # If the user is just visiting the page (GET request), show the empty search form
    return render_template('search.html', papers=None, query=None)

# In app.py, add this new route (e.g., after the home route)

@app.route('/news')
@app.route('/news/page/<int:page>')
def news(page=1):
    news_articles = fetch_rss_feeds()
    
    # Sort articles by published date
    news_articles.sort(key=lambda x: x.get('published_date', ''), reverse=True)
    
    # Paginate the results
    start = (page - 1) * PER_PAGE
    end = start + PER_PAGE
    paginated_articles = news_articles[start:end]
    total_pages = (len(news_articles) // PER_PAGE) + (len(news_articles) % PER_PAGE > 0)
    
    return render_template('news.html',
                           articles=paginated_articles,
                           current_page=page,
                           total_pages=total_pages)

@app.route('/sw.js')
def sw():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'sw.js')

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Creates tables if they don't exist
    app.run(debug=True)
