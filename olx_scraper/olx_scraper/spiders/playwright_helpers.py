"""
Модуль для взаємодії з Playwright у Scrapy.
Містить допоміжні функції для перевірки помилки 403,
паузи виконання скрипта, скролінгу та кліків на елементах сторінки.
"""
from typing import Callable, Awaitable
from scrapy.exceptions import IgnoreRequest
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


# Тип для scrapy_logger – функція, яка приймає повідомлення (str) та рівень логування (int)
# і повертає об'єкт, що очікується (Awaitable), який не повертає значення
LoggerCallable = Callable[[str, int], Awaitable[None]]


async def check_403_error(page: Page, ad_link: str, scrapy_logger: LoggerCallable) -> None:
    """
    Перевіряє сторінку на наявність помилки 403 від CloudFront.

    Якщо на сторінці знайдено заголовок "403 ERROR", функція:
    - Виводить повідомлення в консоль.
    - Логує повідомлення з використанням scrapy_logger.
    - Очікує 45 секунд.
    - Закриває сторінку.
    - Піднімає виключення IgnoreRequest для виключення поточного запиту.

    :param page: Екземпляр Playwright Page.
    :param ad_link: URL оголошення для логування.
    :param scrapy_logger: Функція для логування повідомлень із зазначенням рівня логування.
    :raises IgnoreRequest: Якщо виявлено блокування через CloudFront.
    """
    if await page.locator("h1", has_text="403 ERROR").count() > 0:
        print(f"===== Attention Blocked by CloudFront !!! URL: {ad_link} =====")
        await scrapy_logger(f"===== Attention Blocked by CloudFront Next request in 5 seconds URL: {ad_link} =====", 40)
        await page.wait_for_timeout(45_000)
        await page.close()
        raise IgnoreRequest(f"===== Blocked by CloudFront. URL: {ad_link} =====")


async def page_pause(page: Page, scrapy_logger: LoggerCallable) -> None:
    """
    Призупиняє виконання сторінки за допомогою Playwright.

    Логує повідомлення про паузу сторінки та викликає функцію page.pause().

    :param page: Екземпляр Playwright Page.
    :param scrapy_logger: Функція для логування повідомлень із зазначенням рівня логування.
    """
    await scrapy_logger("===== Page on Pause", 30)
    await page.pause()


async def scroll_to_number_of_views(
    page: Page,
    footer_bar_selector: str,
    user_name_selector: str,
    description_parts_selector: str,
    scrapy_logger: LoggerCallable,
) -> None:
    """
    Скролить сторінку до певних елементів, що містять інформацію (наприклад, кількість переглядів).

    Функція виконує наступне:
    - Очікує появи елемента, що відповідає селектору футер-бару.
    - Якщо селектор футер-бару не з’являється, логує помилку, закриває сторінку та повертається.
    - Скролить до елемента футер-бару.
    - Очікує появи елементів з user_name та description_parts.
    - Логує успішне завантаження сторінки.

    :param page: Екземпляр Playwright Page.
    :param footer_bar_selector: Селектор для елемента футер-бару.
    :param user_name_selector: Селектор для елемента, що містить ім'я користувача.
    :param description_parts_selector: Селектор для елементів опису оголошення.
    :param scrapy_logger: Функція для логування повідомлень із зазначенням рівня логування.
    """
    try:
        await page.wait_for_selector(footer_bar_selector, timeout=20_000)
    except PlaywrightTimeoutError as err:
        await scrapy_logger(
            f"=== Tried to scroll into Number of Views but it's not displayed: {err} ===", 40)
        await page.close()
        return
    try:
        await scrapy_logger(
            "----------------===== Start to scrolling into Number of Views =====-----------------",
            20,
        )
        await page.locator(footer_bar_selector).scroll_into_view_if_needed()
        await page.locator(user_name_selector).first.wait_for(timeout=10_000)
        await page.locator(description_parts_selector).wait_for(timeout=10_000)
        await scrapy_logger(
            "----------------===== Page should have loaded =====-----------------",
            20,
        )
    except PlaywrightTimeoutError as err:
        await scrapy_logger(f"=== Failed to get elements User Name, Description: {err} ===", 40)


async def scroll_and_click_to_show_phone(
    page: Page,
    btn_show_phone_selector: str,
    contact_phone_selector: str,
    scrapy_logger: LoggerCallable
) -> None:
    """
    Скролить сторінку до кнопки "Показати телефон" та виконує клік по ній.

    Функція виконує наступні дії:
    - Логує початок операції скролінгу до кнопки.
    - Очікує появи кнопки за вказаним селектором.
    - Якщо кнопка не з’являється у встановлений час, логує повідомлення та повертається.
    - Скролить до кнопки, логує завершення скролінгу та виконує клік по кнопці.
    - Очікує появи елемента з контактним телефоном.
    - Логує успішне відображення телефону або повідомляє про невдалу спробу.

    :param page: Екземпляр Playwright Page.
    :param btn_show_phone_selector: Селектор для кнопки "Показати телефон".
    :param contact_phone_selector: Селектор для елемента, що містить контактний телефон.
    :param scrapy_logger: Функція для логування повідомлень із зазначенням рівня логування:
    - msg: str, level: int
    :return: None
    """
    try:
        await scrapy_logger("=== Start to scrolling into show phone button ===", 20)
        await page.locator(btn_show_phone_selector).wait_for(timeout=2_000)
    except PlaywrightTimeoutError as err:
        await scrapy_logger(f"===The 'Show phone' button is not displayed: {err} ===", 30)
        return
    await page.locator(btn_show_phone_selector).scroll_into_view_if_needed(
        timeout=1_000
    )
    await scrapy_logger("=== End to scrolling into show phone button ===", 20)
    await page.click(btn_show_phone_selector, timeout=5_000)
    await scrapy_logger("=== The “Show phone” button was clicked ===", 20)
    try:
        await page.locator(contact_phone_selector).last.wait_for(timeout=3_000)
        await scrapy_logger("=== The phone has been displayed successfully ===", 20)
    except PlaywrightTimeoutError:
        await scrapy_logger(
            "=== Phone did not display successfully after clicking the 'Show Phone' button ===", 30)
        return None
    return
