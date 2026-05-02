from threading import Thread

from inspect import getsource
from utils.download import download
from utils import get_logger
import scraper
import time

from report_stats import *


class Worker(Thread):
    def __init__(self, worker_id, config, restart, frontier):
        self.logger = get_logger(f"Worker-{worker_id}", "Worker")
        self.config = config
        self.restart = restart
        self.frontier = frontier
        # basic check for requests in scraper
        assert {getsource(scraper).find(req) for req in {"from requests import", "import requests"}} == {-1}, "Do not use requests in scraper.py"
        assert {getsource(scraper).find(req) for req in {"from urllib.request import", "import urllib.request"}} == {-1}, "Do not use urllib.request in scraper.py"
        super().__init__(daemon=True)
        
    def run(self):
        while True:
            tbd_url = self.frontier.get_tbd_url()
            if not tbd_url:
                self.logger.info("Frontier is empty. Stopping Crawler.")
                break
            resp = download(tbd_url, self.config, self.logger)
            self.logger.info(
                f"Downloaded {tbd_url}, status <{resp.status}>, "
                f"using cache {self.config.cache_server}.")
            scraped_urls = scraper.scraper(tbd_url, resp, self.config, self.restart)
            for scraped_url in scraped_urls:
                self.frontier.add_url(scraped_url)
            self.frontier.mark_url_complete(tbd_url)
            time.sleep(self.config.time_delay)

        try:
            with open("report.txt", "w") as f:
                print_report(f)
        except Exception as e:
            print (f"Error outputting report: {e}")
