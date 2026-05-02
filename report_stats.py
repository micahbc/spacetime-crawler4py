import sys
import signal


visited_urls = {}
longest_page = ["", 0]
word_fequencies = {}
subdomains = {}


def computeWordFrequencies(tokens):
    for token in tokens:
        if token not in word_fequencies:
            word_fequencies[token] = 1
        else:
            word_fequencies[token] += 1


def printFrequencies():
    sorted_map = list(word_fequencies.items())
    sorted_map.sort(key=lambda tup: tup[1], reverse=True)
    i = 0
    for pair in sorted_map:
        if i >= 50:
            break
        i += 1
        print (f'\t{i}. {pair[0]}, {pair[1]}')


def print_report(out):
    print (f'(1) Unique pages:\n\t {len(visited_urls)}', file=out)
    print (f'\n(2) Longest page:\n\t {longest_page[0]}, {longest_page[1]}', file=out)
    print ("\n(3) Common words: ", file=out)
    printFrequencies()
    print ("\n(4) Subdomains: ", file=out)
    sorted_subdomains = dict(sorted(subdomains.items()))
    for key, value in sorted_subdomains.items():
        print (f'\t{key}, {value}', file=out)


# temporary, for debug
def signal_handler(signum, frame):
    print ("Signal received")
    print_report(sys.stdout)
    sys.exit()

signal.signal(signal.SIGINT, signal_handler)
