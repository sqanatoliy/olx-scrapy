import logging
import re
from datetime import datetime
from typing import Iterator, AsyncGenerator, Any
import typing

import scrapy
from parsel import Selector
from scrapy.http import Response
from scrapy.selector.unified import SelectorList
from scrapy_playwright.page import PageMethod

from ..items import OlxScraperItem
from .playwright_helpers import (
    check_403_error,
    scroll_to_number_of_views,
    scroll_and_click_to_show_phone,
)


# ADS LIST PAGE
ADS_BLOCK_SELECTOR = 'div[data-testid="l-card"]'
AD_TITLE_URL_SELECTOR = ' div[data-cy="ad-card-title"] a'
AD_TITLE_SELECTOR = ' div[data-cy="ad-card-title"] a > h4'
AD_PRICE_SELECTOR = ' p[data-testid="ad-price"]'
AD_LOCATION_AND_DATE_SELECTOR = ' p[data-testid="location-date"]'

# AD DETAIL PAGE

# Contact section

AD_PUB_DATE_SELECTOR = 'span[data-cy="ad-posted-at"]'
BTN_SHOW_PHONE_SELECTOR = 'button[data-testid="show-phone"]'
CONTACT_PHONE_SELECTOR = 'a[data-testid="contact-phone"]'
# User profile
USER_NAME_SELECTOR = 'a[data-testid="user-profile-link"] h4'
USER_SCORE_SELECTOR = 'article[data-testid="score-widget"] > div > p'
USER_REGISTRATION_SELECTOR = 'a[data-testid="user-profile-link"] > div > div > p > span'
USER_LAST_SEEN_SELECTOR = 'p[data-testid="lastSeenBox"] > span'
# Location
MAP_OVERLAY_SELECTOR = 'div[data-testid="qa-map-overlay-hidden"]'
# Photo section
BLOCK_WITH_PHOTO_SELECTOR = 'div[data-testid="ad-photo"]'
# Description section
AD_TAGS_SELECTOR = 'div[data-testid="qa-advert-slot"] + ul'
DESCRIPTION_PARTS_SELECTOR = 'div[data-cy="ad_description"] > div'
# Description section footer
FOOTER_BAR_SELECTOR = 'div[data-testid="ad-footer-bar-section"]'
AD_ID_SELECTOR = 'normalize-space(//div[@data-testid="ad-footer-bar-section"]/span)'
AD_VIEW_COUNTER_SELECTOR = '//span[@data-testid="page-view-counter"]/text()'


class OlxSpider(scrapy.Spider):
    """Scraper for olx.ua/list"""
    name = "olx"
    allowed_domains: list[str] = ["olx.ua"]
    start_urls: list[str] = [
        f"https://www.olx.ua/uk/list/?page={i}" for i in range(1, 6)
    ]

    def start_requests(self) -> Iterator[scrapy.Request]:
        """Override start_requests to include Playwright meta"""
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                meta={
                    "playwright": True,
                    "playwright_context": "new",
                    "playwright_context_kwargs": {
                        "ignore_https_errors": True,
                        "viewport": {"width": 1980, "height": 1020},
                        # "proxy": {
                        #     "server": "http://proxy.toolip.io:31114",
                        #     "username": "tl-d8582f18f76fecabd2f916e4bd0df4cf63c9f54cd0c1b3d14529591b9ffac8c7-country-us-session-c9166",
                        #     "password": "t6yqmxldm870",
                        # },
                    },
                    "playwright_page_methods": [
                        PageMethod(check_403_error, url, self.scrapy_logger),
                        PageMethod(
                            "wait_for_selector", AD_TITLE_URL_SELECTOR, timeout=10_000
                        ),  # Wait for all network requests
                    ],
                },
                errback=self.errback_close_page,
            )

    def parse(self, response: Response) -> Iterator[scrapy.Request]:
        """Get all urls"""
        ads_block: SelectorList = response.css(ADS_BLOCK_SELECTOR)
        if not ads_block:
            self.log("No ads found on the page!", level=scrapy.logging.WARNING)
            return
        for ad in ads_block[:]:
            ad_link: str | None = (
                ad.css(AD_TITLE_URL_SELECTOR).css("::attr(href)").get()
            )
            ad_title: str | None = ad.css(AD_TITLE_SELECTOR).css("::text").get()
            ad_price: str | None = ad.css(AD_PRICE_SELECTOR).css("::text").get()
            if ad_link and ad_title:
                full_url: str = response.urljoin(ad_link)
                self.log(f"Collected URL: {full_url}", level=logging.INFO)
                self.log(f"Collected TITLE: {ad_title}", level=logging.INFO)
                self.log(f"Collected PRICE: {ad_price}", level=logging.INFO)
                # Create Item and fill fields
                item:OlxScraperItem = OlxScraperItem()
                item["title"] = ad_title.strip()
                item["price"] = ad_price.strip() if ad_price else None
                item["url"] = full_url.strip()
                yield scrapy.Request(
                    url=full_url,
                    callback=self.parse_ad,
                    meta={
                        "item": item,
                        "playwright": True,
                        "playwright_include_page": True,
                        "playwright_context": "new",
                        "playwright_context_kwargs": {
                            "ignore_https_errors": True,
                            "viewport": {"width": 1980, "height": 1020},
                            # "proxy": {
                            #     "server": "http://proxy.toolip.io:31114",
                            #     "username": "tl-d8582f18f76fecabd2f916e4bd0df4cf63c9f54cd0c1b3d14529591b9ffac8c7-country-us-session-c9166",
                            #     "password": "t6yqmxldm870",
                            # },
                        },
                        "playwright_page_methods": [
                            PageMethod(check_403_error, full_url, self.scrapy_logger),
                            PageMethod(
                                scroll_to_number_of_views,
                                FOOTER_BAR_SELECTOR,
                                USER_NAME_SELECTOR,
                                DESCRIPTION_PARTS_SELECTOR,
                                self.scrapy_logger,
                            ),
                            PageMethod(
                                "wait_for_load_state", "domcontentloaded", timeout=10000
                            ),
                            # PageMethod(page_pause),
                        ],
                    },
                    errback=self.errback_close_page,
                )

    async def parse_ad(self, response: Response) -> AsyncGenerator[OlxScraperItem, None]:
        """Processing the detailed page of the ad"""
        page: Any = response.meta["playwright_page"]
        try:
            item: OlxScraperItem = response.meta["item"]

            # Ad publication date
            ad_pub_date: str | None = response.css(AD_PUB_DATE_SELECTOR).css("::text").get()

            # User profile
            user_name: str | None = response.css(USER_NAME_SELECTOR).css("::text").get()
            user_score: str | None = response.css(USER_SCORE_SELECTOR).css("::text").get()
            user_registration: str | None = (
                response.css(USER_REGISTRATION_SELECTOR).css("::text").get()
            )
            user_last_seen: str | None = (
                response.css(USER_LAST_SEEN_SELECTOR).css("::text").get()
            )

            # Location
            map_overlay = response.css(MAP_OVERLAY_SELECTOR)
            location_section = map_overlay.xpath("..")
            location_parts: list[str] = location_section.css("svg + div *::text").getall()
            location: str = " ".join(locat.strip() for locat in location_parts if locat)

            # block with urls on the photos
            block_with_photos = response.css(BLOCK_WITH_PHOTO_SELECTOR)
            # Get all src values from img tags
            img_urls_list: list[str] = []
            for div in block_with_photos:
                img_srcs: list[str] = div.css("img::attr(src)").getall()
                img_urls_list.extend(img_srcs)

            # Announcement tags
            ad_tags: list[str | None] = (
                response.css(AD_TAGS_SELECTOR).css("*::text").getall()
            )
            # Announcement description
            description_parts: list[str] = (
                response.css(DESCRIPTION_PARTS_SELECTOR).css("::text").getall()
            )
            description: str = " ".join(part.strip() for part in description_parts if part)
            # Announcement ID
            ad_id: str | None = response.xpath(AD_ID_SELECTOR).get()
            ad_view_counter: str | None = response.xpath(AD_VIEW_COUNTER_SELECTOR).get()

            item["ad_pub_date"] = ad_pub_date
            item["user_name"] = user_name.strip() if user_name else None
            item["user_score"] = user_score if user_score else None
            item["user_registration"] = (
                user_registration.strip() if user_registration else None
            )
            item["user_last_seen"] = user_last_seen
            item["announcement_id"] = ad_id
            item["announcement_view_counter"] = (
                ad_view_counter if ad_view_counter else None
            )
            item["location"] = location.strip() if location else None
            item["ad_tags"] = ad_tags
            item["description"] = description if description else None
            item["img_src_list"] = img_urls_list

            await scroll_and_click_to_show_phone(
                page,
                BTN_SHOW_PHONE_SELECTOR,
                CONTACT_PHONE_SELECTOR,
                self.scrapy_logger,
            )
            page_content: Any = await page.content()
            new_html = Selector(text=page_content)

            phone_number: str | None = (
                new_html.css(CONTACT_PHONE_SELECTOR).css("::text").get()
            )
            item["phone_number"] = phone_number if phone_number else None
            self.log(f"Phone is {phone_number}", level=logging.INFO)
            # Save data
            yield item
            await page.close()
            # await page.context.close()
        except Exception as e:
            self.logger.error(f"Error in parse_ad: {e}")
            await page.close()
            raise

    async def errback_close_page(self, failure) -> None:
        meta: Any = failure.request.meta
        if "playwright_page" in meta:
            page: Any = meta["playwright_page"]
            await page.close()

    async def scrapy_logger(self, message: str, level: int = 20) -> None:
        """Scrapy logger for Playwright"""
        self.logger.log(level, message)

    @staticmethod
    def parse_date(input_str) -> str:
        """Parse a string with a date and returns it in the '15 січня 2025 р.' format."""
        today: datetime = datetime.now()
        months_uk: dict[int, str] = {
            1: "січня",
            2: "лютого",
            3: "березня",
            4: "квітня",
            5: "травня",
            6: "червня",
            7: "липня",
            8: "серпня",
            9: "вересня",
            10: "жовтня",
            11: "листопада",
            12: "грудня",
        }
        if input_str.startswith("Сьогодні"):
            full_date: str = today.strftime(f"%d {months_uk[today.month]} %Y р.")
        else:
            match: re.Match[str] | None = re.match(
                r"(\d{1,2}) ([а-яіїє]+) (\d{4}) р\.", input_str
            )
            if not match:
                raise ValueError(f"Некоректний формат дати: {input_str}")
            day: str | typing.Any = match.group(1).zfill(2)
            month: str | typing.Any = match.group(2)
            year: str = match.group(3)
            if month not in months_uk.values():
                raise ValueError(f"Некоректний місяць у даті: {month}")
            full_date = f"{day} {month} {year} р."
        return full_date
