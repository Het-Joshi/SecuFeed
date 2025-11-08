# Import the 'arxiv' library
import arxiv

def search_for_papers(keyword, max_results=10):
    """
    Searches for papers on arXiv based on a keyword.

    Args:
        keyword (str): The search term (e.g., "cryptography").
        max_results (int): The maximum number of results to return.

    Returns:
        list: A list of dictionaries, where each dictionary contains
              details of a paper.
    """
    print(f"Searching for the latest {max_results} papers on '{keyword}'...")

    # Create a search object. We sort by the last updated date to get the newest papers.
    search = arxiv.Search(
        query=keyword,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.LastUpdatedDate
    )

    # This list will hold our formatted paper information
    found_papers = []

    # The search.results() function returns a generator of Result objects
    for result in search.results():
        # For each result, we'll store the info we care about in a dictionary
        paper_info = {
            "title": result.title,
            "summary": result.summary,
            "authors": [author.name for author in result.authors],
            "published_date": result.published.strftime("%Y-%m-%d"),
            "pdf_link": result.pdf_url
        }
        found_papers.append(paper_info)

    return found_papers

# --- Main part of the script ---
if __name__ == "__main__":
    # Define the field of interest we want to search for
    field_of_interest = "network security"
    
    # Call our function to get the papers
    papers = search_for_papers(field_of_interest)

    # Check if we found any papers
    if not papers:
        print(f"No papers found for the keyword '{field_of_interest}'.")
    else:
        # Loop through the papers and print their details
        print("\n--- Found Papers ---")
        for i, paper in enumerate(papers, 1):
            print(f"\n{i}. Title: {paper['title']}")
            print(f"   Authors: {', '.join(paper['authors'])}")
            print(f"   Published: {paper['published_date']}")
            print(f"   Link: {paper['pdf_link']}")
            # We'll print a shortened summary for readability
            print(f"   Summary: {paper['summary']}")
