import re
import os
import hashlib
from urllib.parse import urlparse
from urllib.parse import parse_qsl
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from datetime import datetime
import shelve

from report_stats import *

_loaded_stats = False
_stats_dict = {}

_DEBUG = False

_MAX_CALENDER = 5
_MIN_CALENDER = 2010
_current_year = datetime.now().year

_MAX_CONTENT_LENGTH = 10 * 1024 * 1024 # capping at 10 MB because 11 MB was flagged by a 607 error in the log during testing
_SIMILARITY_THRESHOLD = 0.9
_MODULUS_TO_USE_TO_DETERMINE_SIMILARITY = 4
_N_GRAM_SIZE = 3
_page_hash_set = {}

_robot_parsers = {}

try:
    with open("stopwords.txt", "r") as _f:
        _stop_words = frozenset(line.strip().lower() for line in _f if line.strip())
except Exception:
    _stop_words = frozenset()


def _load_stats(config, restart):
    '''Loads the stats from the shelve file. 
    This is used to keep track of the pages and their statistics 
    we have seen before, even if the crawler restarts.'''
    global _loaded_stats, visited_urls, longest_page, word_fequencies, subdomains #global variables to stop local invisible copies per run of the func
    try:

        ''' in case of restart '''
        if not os.path.exists(config.stats_file) and not restart:
            # Stats file does not exist, but request to load stats.
            if(_DEBUG):
                print (f"Did not find stats file {config.stats_file}, starting from seed.")
        elif os.path.exists(config.stats_file) and restart:
            # Stats file does exists, but request to start from seed.
            if(_DEBUG):
                print (f"Found stats file {config.stats_file}, deleting it.")
            os.remove(config.stats_file)

        '''open shelve file from the config.ini and load the stats into the _stats_dict.'''
        stats_file = config.stats_file
        with shelve.open(stats_file) as db: # using shelve as a persistent dict-like database with var names from report_stats.py
            if "visited_urls" in db:
                visited_urls.update(db["visited_urls"])
            if "longest_page" in db:
                stored = db["longest_page"]
                longest_page[0] = stored[0]
                longest_page[1] = stored[1]
            if "word_fequencies" in db:
                word_fequencies.update(db["word_fequencies"])
            if "subdomains" in db:
                subdomains.update(db["subdomains"])
    except Exception as e:
        if(_DEBUG):
            print()
            print("Error loading stats with exception: ", e)
            print()   
    finally:
        _loaded_stats = True
        
        
def _write_stats(config):
    '''Writes the stats to the shelve file. 
    This is used to keep track of the pages and their statistics 
    we have seen before, even if the crawler restarts.'''
    try:
        '''open shelve file from the config.ini and write the stats from the _stats_dict into it.'''
        stats_file = config.stats_file
        with shelve.open(stats_file) as db: # open shelve with context manager, writes stats
            db["visited_urls"] = visited_urls
            db["longest_page"] = longest_page
            db["word_fequencies"] = word_fequencies
            db["subdomains"] = subdomains
    except Exception as e:
        if(_DEBUG):
            print()
            print("Error writing stats with exception: ", e)
            print()

def _n_gram_hasher(tokens):
    '''Hashes an n-gram. Returns a hash number.'''
    h = 8675309
    for char in tokens:
        h ^= ord(char)
        h = (h * 0x100000001b3) & 0xffffffffffffffff
    return h

def _validate_page_similarity(url, resp, config):
    '''Calculates the hash of the page content. If the hash is already in the _page_hash_set,
    or if the similarity of the page content with any of the previously seen pages is above 
    the _SIMILARITY_THRESHOLD, it means we have seen already and return False. 
    Otherwise, add the hash to the _page_hash_set and return True.
    If the crawler restarts, then the _page_hash_set will be empty and will start from scratch.'''
    if resp.status != 200:
        if(_DEBUG):
            print()
            print("Invalid status code: ", resp.status, url)
            print()
        return True # Don't reject based on status code, but log it for debugging purposes
    
    # Check content length to avoid crawling very large files with low information value
    # and to avoid parsing the large files here
    content_length = resp.raw_response.headers.get('content-length')
    
    if content_length:
        # Headers are always strings, so you must cast to an integer to compare
        if int(content_length) > _MAX_CONTENT_LENGTH:
            if(_DEBUG):
                print()
                print(f"Rejected: Page too large ({content_length} bytes): ", url)
                print()
            return False
        
    content_type = resp.raw_response.headers.get('content-type')
    content_type = str(content_type).lower() # Convert to string and lowercase for easy checking

    # choose between xml or html parser based on content type
    if 'xml' in content_type:
        soup = BeautifulSoup(resp.raw_response.text, 'xml')
    else:
        soup = BeautifulSoup(resp.raw_response.text, 'html.parser')
    
    # parse page into tokens
    if(_DEBUG):
        print()
        print("Parsing page: ", url)
        print()
    soup = BeautifulSoup(resp.raw_response.text, 'html.parser')
    text = soup.get_text()
    tokens = re.findall(r'\b\w+\b', text.lower())

    word_count = len(tokens)
    if word_count < _N_GRAM_SIZE:
        return False # Reject low-information pages

    ''' For report '''
    if word_count > longest_page[1]:
        longest_page[0] = url
        longest_page[1] = word_count

    ''' For report '''
    filtered_tokens = [t for t in tokens if t not in _stop_words] # filtering tokens not in stopwords before calling computeWordFrequencies
    computeWordFrequencies(filtered_tokens)

    n_gram_hashes = set()
    for i in range(word_count - _N_GRAM_SIZE + 1):
        # n_gram tokens and join them directly into a string
        n_gram_str = ''.join(tokens[i:i + _N_GRAM_SIZE])
        curr = _n_gram_hasher(n_gram_str)
    
        if curr % _MODULUS_TO_USE_TO_DETERMINE_SIMILARITY == 0:
            n_gram_hashes.add(curr)
    
    # calculate similarity
    for existing_hashes in _page_hash_set.values():
        intersection = len(n_gram_hashes & existing_hashes)
        union = len(n_gram_hashes | existing_hashes)
        if union > 0:
            similarity = intersection / union
            if similarity > _SIMILARITY_THRESHOLD:
                return False
    
    # else, add hash to set and return True
    _page_hash_set[url] = n_gram_hashes
    if(_DEBUG):
            print()
            print("New page added to hash: ", url)
            print()
    _write_stats(config) # called after all is validated to write the stats for the report
    return True

def _can_fetch_url_robots(url):
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = _robot_parsers.get(robots_url)
        if parser is None:
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
            except Exception:
                parser = None
            _robot_parsers[robots_url] = parser
        if parser is None:
            return True
        return parser.can_fetch("*", url)
    except Exception:
        return True


def scraper(url, resp, config, restart):
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
    if not _loaded_stats:
        _load_stats(config, restart)

    if not _validate_page_similarity(url, resp, config):
            return []
    else:
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

    #hashed = hash(url)
    #if hashed not in visited_urls:
    #    visited_urls[hashed] = [url]
    #elif url not in visited_urls[hashed]:
    #    visited_urls[hashed].append(url)

    hyperlinks = []
    try:
        if resp.status == 200:
            '''
            https://beautiful-soup-4.readthedocs.io/en/latest/#quick-start
            '''
            soup = BeautifulSoup(resp.raw_response.text, 'html.parser')
            for link in soup.find_all('a'):
                link = link.get('href')
                if link:
                    defragmented = link.split("#")[0]
                    hashed = hash(defragmented)
                    if hashed not in visited_urls:
                        hyperlinks.append(defragmented)
                        #visited_urls[hashed] = [defragmented]
                    elif defragmented not in visited_urls[hashed]:
                        hyperlinks.append(defragmented)
                        #visited_urls[hashed].append(defragmented)
    except Exception as e:
        print (f"Error: {e}")

    return set(hyperlinks)

def is_valid(url):
    # Decide whether to crawl this url or not. 
    # If you decide to crawl it, return True; otherwise return False.
    # There are already some conditions that return False.
    try:
        parsed = urlparse(url)

        if parsed.scheme not in set(["http", "https"]):
            return False

        if parsed.hostname:
            if ("cs.uci.edu" not in parsed.hostname) and ("informatics.uci.edu" not in parsed.hostname) and ("stat.uci.edu" not in parsed.hostname):
                return False
            else:
                ''' For report '''
                if parsed.hostname not in subdomains:
                    subdomains[parsed.hostname] = 1
                else:
                    subdomains[parsed.hostname] += 1

        if "ical=1" in parsed.query:
            return False

        if "redirect_to" in parsed.query:
            return False

        if "/events/tag/talk/" in parsed.path:
            # https://isg.ics.uci.edu/events/tag/talk/month
            if "month" in parsed.path:
                pass
            # https://isg.ics.uci.edu/events/tag/talk/list/?tribe-bar-date=2032-12-01
            elif "list" in parsed.path:
                date = dict(parse_qsl(parsed.query)).get("tribe-bar-date")
                if date:
                    year = int( date.split("-")[0] )
                    if year > (_current_year + _MAX_CALENDER):
                        return False
                    if year < _MIN_CALENDER:
                        return False
            # https://isg.ics.uci.edu/events/tag/talk/2032-09
            # https://isg.ics.uci.edu/events/tag/talk/day/2032-06-02
            else:
                year = int( parsed.path.split("/")[-1].split("-")[0] )
                if year > (_current_year + _MAX_CALENDER):
                        return False
                if year < _MIN_CALENDER:
                    return False

        if not _can_fetch_url_robots(url):
            if(_DEBUG):
                print()
                print("Blocked by robots.txt: ", url)
                print()
            return False

        if re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz|sql|ppsx)$", parsed.path.lower()):
            return False
        
        if re.search(r"http://instance1_public_ip:8080/" +
             r"|wics\.ics\.uci\.edu/events/|wics\.ics\.uci\.edu.*\?share=", url.lower()):
            if(_DEBUG):
                print()
                print("Blocked by trap blacklist rules: ", url)
                print()
            return False
        
        hashed = hash(url)
        if hashed not in visited_urls:
            visited_urls[hashed] = [url]
        elif url not in visited_urls[hashed]:
            visited_urls[hashed].append(url)
        
        return True

    except TypeError:
        print ("TypeError for ", parsed)
        raise

    # parsed = urlparse(url)
    # ValueError: 'YOUR_IP' does not appear to be an IPv4 or IPv6 address
    except ValueError:
        print ("ValueError for ", url)
        return False

    except Exception as e:
        print (f"Error: {e}")
        return False
