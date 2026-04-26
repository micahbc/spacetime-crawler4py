import re
import time
from urllib.parse import urlparse
from bs4 import BeautifulSoup

def scraper(url, resp):
    '''In this project. we are looking for text in Web pages so that we
    can search it later on. The following is a list of what a "correct crawl"
    entails in this context:

    Honor the politeness delay for each site
    Crawl all pages with high textual information content
    Detect and avoid infinite traps
    Detect and avoid sets of similar pages with no information
    Detect and avoid dead URLs that return a 200 status but no data.
    Detect and avoid crawling very large files, especially if they
    have low information value.
    For most of these requirements, the only way you can detect these problems
    is by first monitoring where your crawler is going, and then adjusting its
    behavior in order to stay away from problematic pages.
    '''
    time.sleep(5)
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]

def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content
    hyperlinks = []
    try:
        if resp.status == 200:
            '''
            https://beautiful-soup-4.readthedocs.io/en/latest/#quick-start
            '''
            soup = BeautifulSoup(resp.raw_response.text, 'html.parser')
            for link in soup.find_all('a'):
                hyperlinks.append(link.get('href'))
    except:
        print ("Error: extract_next_links")

    return set(hyperlinks)

def is_valid(url):
    # Decide whether to crawl this url or not. 
    # If you decide to crawl it, return True; otherwise return False.
    # There are already some conditions that return False.
    try:
        parsed = urlparse(url)
        if parsed.hostname:
            if ("ics.uci.edu" or "cs.uci.edu" or "informatics.uci.edu" or "stat.uci.edu") not in parsed.hostname:
                return False
        if parsed.scheme not in set(["http", "https"]):
            return False
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz)$", parsed.path.lower())

    except TypeError:
        print ("TypeError for ", parsed)
        raise
