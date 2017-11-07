#!/usr/bin/env python

"""
Sushi Chef for Touchable Earth: http://www.touchableearth.org/
Consists of videos and images.
Supports multiple languages -- just create another subclass of TouchableEarthChef!
"""

import os
import re
import requests
import tempfile
import time
import urllib
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
import pycountry
import youtube_dl
import moviepy.editor as mpe

from le_utils.constants import content_kinds, file_formats, languages
from ricecooker.chefs import SushiChef
from ricecooker.classes import nodes, files, licenses
from ricecooker.utils.caching import CacheForeverHeuristic, FileCache, CacheControlAdapter, InvalidatingCacheControlAdapter
from ricecooker.utils.browser import preview_in_browser
from ricecooker.utils.html import download_file
from ricecooker.utils.zip import create_predictable_zip
from ricecooker import config


sess = requests.Session()
cache = FileCache('.webcache')
forever_adapter = CacheControlAdapter(heuristic=CacheForeverHeuristic(), cache=cache)
ydl = youtube_dl.YoutubeDL({
    'quiet': True,
    'no_warnings': True,
    'writesubtitles': True,
    'allsubtitles': True,
})

sess.mount('http://www.touchableearth.org', forever_adapter)

TE_LICENSE = licenses.SpecialPermissionsLicense(
    description="Permission has been granted by Touchable Earth to"
    " distribute this content through Kolibri.",
    copyright_holder="Touchable Earth Foundation (New Zealand)"
)


class TouchableEarthChef(SushiChef):
    """
    The chef class that takes care of uploading channel to the content curation server.

    We'll call its `main()` method from the command line script.

    NOTE: Do no directly instantiate. This is an abstract base class.
    Subclasses must provide the channel_info class property. See examples
    below.
    """
    def construct_channel(self, **kwargs):
        """
        Create ChannelNode and build topic tree.
        """
        channel = self.get_channel()
        add_countries_to_channel(channel, channel.language)
        return channel


class EnglishChef(TouchableEarthChef):
    channel_info = {
        'CHANNEL_SOURCE_DOMAIN': "www.touchableearth.org",
        'CHANNEL_SOURCE_ID': "touchable-earth",
        'CHANNEL_TITLE': "Touchable Earth",
        'CHANNEL_THUMBNAIL': "https://d1iiooxwdowqwr.cloudfront.net/pub/appsubmissions/20140218003206_PROFILEPHOTO.jpg",
        'CHANNEL_LANGUAGE': 'en',
        'CHANNEL_DESCRIPTION': 'Where kids teach kids about the world. Taught entirely by school age children in short videos, Touchable Earth promotes tolerance for gender, culture, and identity.',
    }


class FrenchChef(TouchableEarthChef):
    channel_info = {
        'CHANNEL_SOURCE_DOMAIN': "www.touchableearth.org",
        'CHANNEL_SOURCE_ID': "touchable-earth-french",
        'CHANNEL_TITLE': "Touchable Earth (fr)",
        'CHANNEL_THUMBNAIL': "https://d1iiooxwdowqwr.cloudfront.net/pub/appsubmissions/20140218003206_PROFILEPHOTO.jpg",
        'CHANNEL_LANGUAGE': 'fr',
        'CHANNEL_DESCRIPTION': 'Where kids teach kids about the world. Taught entirely by school age children in short videos, Touchable Earth promotes tolerance for gender, culture, and identity.',
    }


def add_countries_to_channel(channel, language):
    doc = get_parsed_html_from_url("http://www.touchableearth.org/places/")
    places = doc.select("div.places-row a.custom-link")

    for place in places:
        title = place.text.strip()
        href = place["href"]
        url = "%s?lang=%s" % (href, language)
        channel.add_child(scrape_country(title, url, language))


def scrape_country(title, country_url, language):
    """
    title: China
    country_url: http://www.touchableearth.org/china-facts-welcome/?lang=fr
    """
    print("Scraping country node: %s (%s)" % (title, country_url))

    doc = get_parsed_html_from_url(country_url)
    country = doc.select_one(".breadcrumbs .taxonomy.category")
    href = country["href"]
    title = country.text.strip()

    topic = nodes.TopicNode(source_id=href, title=title)
    add_topics_to_country(doc, topic, language)
    return topic


def add_topics_to_country(doc, country_node, language):
    """
    country_url: http://www.touchableearth.org/china/
    """
    topic_options = doc.select(".sub_cat_dropdown .select_option_subcat option")
    topic_urls_added = set()

    for option in topic_options:
        if option.has_attr("selected"):
            continue

        url = option["value"]
        title = option.text.strip()

        # Skip duplicates
        if url in topic_urls_added:
            continue
        else:
            topic_urls_added.add(url)

        country_node.add_child(scrape_category(title, url, language))


def scrape_category(title, category_url, language):
    """
    title: Culture
    category_url: http://www.touchableearth.org/china/culture/
        ... redirects to: http://www.touchableearth.org/china-culture-boys-clothing/
    """
    print("  Scraping category node: %s (%s)" % (title, category_url))

    category_node = nodes.TopicNode(source_id=category_url, title=title)

    # Iterate over each item in the "subway" sidebar menu on the left.
    doc = get_parsed_html_from_url(category_url)
    content_items = doc.select(".post_title_sub .current_post")
    slugs_added = set()

    for content in content_items:
        slug = content.select_one(".get_post_title")["value"]

        # Skip duplicates ... seems like the Touchable Earth website has them!
        if slug in slugs_added:
            continue
        else:
            slugs_added.add(slug)

        title = content.select_one(".get_post_title2")["value"]
        site_url = content.select_one(".site_url")["value"]
        url = "%s/%s?lang=%s" % (site_url, slug, language)
        content_node = scrape_content(title, url)
        if content_node:
            category_node.add_child(content_node)

    return category_node


_LANGUAGE_NAME_LOOKUP = {l.name: l for l in languages.LANGUAGELIST}


def getlang_patched(language):
    """A patched version of languages.getlang that tries to fallback to
    a closest match if not found."""
    if languages.getlang(language):
        return language

    # Try matching on the prefix: e.g. zh-Hans --> zh
    first_part = language.split('-')[0]
    if languages.getlang(first_part):
        return first_part

    # See if pycountry can find this language and if so, match by language name
    # to resolve other inconsistencies.  e.g. YouTube might use "zu" while
    # le_utils uses "zul".
    pyc_lang = pycountry.languages.get(alpha_2=first_part)
    if pyc_lang:
        return _LANGUAGE_NAME_LOOKUP.get(pyc_lang.name)

    return None


class LanguagePatchedYouTubeSubtitleFile(files.YouTubeSubtitleFile):
    """Patches ricecooker's YouTubeSubtitleFile to account for inconsistencies
    between YouTube's language codes and those in `le-utils`:

    https://github.com/learningequality/le-utils/issues/23

    TODO(davidhu): This is a temporary fix and the code here should properly be
    patched in `le-utils.constants.languages.getlang` and a small change to
    `ricecooker.classes.files.YouTubeSubtitleFile`.
    """

    def __init__(self, youtube_id, youtube_language, **kwargs):
        self.youtube_language = youtube_language
        language = getlang_patched(youtube_language)
        super(LanguagePatchedYouTubeSubtitleFile, self).__init__(
                youtube_id=youtube_id, language=language, **kwargs)

    def download_subtitle(self):
        settings = {
            'skip_download': True,
            'writesubtitles': True,
            'subtitleslangs': [self.youtube_language],
            'subtitlesformat': "best[ext={}]".format(file_formats.VTT),
            'quiet': True,
            'no_warnings': True
        }
        download_ext = ".{lang}.{ext}".format(lang=self.language, ext=file_formats.VTT)
        return files.download_from_web(self.youtube_url, settings,
                file_format=file_formats.VTT, download_ext=download_ext)


WATERMARK_SETTINGS = {
    "image": "watermark.png",
    "height": 68,
    "right": 16,
    "bottom": 16,
    "position": ("right", "bottom"),
}

# TODO(davidhu): Move this function to Ricecooker to be reuseable. This also
# uses a lot of Ricecooker abstractions, so it'd also be better there for
# encapsulation.
def watermark_video(filename):
    # Check if we've processed this file before -- is it in the cache?
    key = files.generate_key("WATERMARKED", filename, settings=WATERMARK_SETTINGS)
    if not config.UPDATE and files.FILECACHE.get(key):
        return files.FILECACHE.get(key).decode('utf-8')

    # Create a temporary filename to write the watermarked video.
    tempf = tempfile.NamedTemporaryFile(
            suffix=".{}".format(file_formats.MP4), delete=False)
    tempf.close()
    tempfile_name = tempf.name

    # Now watermark it with the Touchable Earth logo!
    print("\t--- Watermarking ", filename)

    video_clip = mpe.VideoFileClip(config.get_storage_path(filename), audio=True)

    logo = (mpe.ImageClip(WATERMARK_SETTINGS["image"])
                .set_duration(video_clip.duration)
                .resize(height=WATERMARK_SETTINGS["height"])
                .margin(right=WATERMARK_SETTINGS["right"],
                    bottom=WATERMARK_SETTINGS["bottom"], opacity=0)
                .set_pos(WATERMARK_SETTINGS["position"]))

    composite = mpe.CompositeVideoClip([video_clip, logo])
    composite.duration = video_clip.duration
    composite.write_videofile(tempfile_name, threads=4)

    # Now move the watermarked file to Ricecooker storage and hash its name
    # so it can be validated.
    watermarked_filename = "{}.{}".format(
        files.get_hash(tempfile_name), file_formats.MP4)
    files.copy_file_to_storage(watermarked_filename, tempfile_name)
    os.unlink(tempfile_name)

    files.FILECACHE.set(key, bytes(watermarked_filename, "utf-8"))
    return watermarked_filename


class WatermarkedYouTubeVideoFile(files.YouTubeVideoFile):
    """A subclass of YouTubeVideoFile that watermarks the video in
    a post-process step.
    """
    def process_file(self):
        filename = super(WatermarkedYouTubeVideoFile, self).process_file()
        self.filename = watermark_video(filename)
        print("\t--- Watermarked ", self.filename)
        return self.filename


def scrape_content(title, content_url):
    """
    title: Boys' clothing
    content_url: http://www.touchableearth.org/china-culture-boys-clothing/
    """
    print("    Scraping content node: %s (%s)" % (title, content_url))

    doc = get_parsed_html_from_url(content_url)
    if not doc:  # 404
        return None

    description = create_description(doc)
    source_id = doc.select_one(".current_post.active .post_id")["value"]

    base_node_attributes = {
        "source_id": source_id,
        "title": title,
        "license": TE_LICENSE,
        "description": description,
    }

    youtube_iframe = doc.select_one(".video-container iframe")
    if youtube_iframe:
        youtube_url = doc.select_one(".video-container iframe")["src"]
        youtube_id = get_youtube_id_from_url(youtube_url)

        if not youtube_id:
            print("    *** WARNING: youtube_id not found for content url", content_url)
            print("    Skipping.")
            return None

        try:
            info = ydl.extract_info(youtube_url, download=False)
            subtitles = info.get("subtitles")
            subtitle_languages = subtitles.keys() if subtitles else []
            print ("      ... with subtitles in languages:", subtitle_languages)
        except youtube_dl.DownloadError as e:
            # Some of the videos have been removed from the YouTube channel --
            # skip creating content nodes for them entirely so they don't show up
            # as non-loadable videos in Kolibri.
            print("        NOTE: Skipping video download due to error: ", e)
            return None

        video_node = nodes.VideoNode(
            **base_node_attributes,
            derive_thumbnail=True,
            files=[WatermarkedYouTubeVideoFile(youtube_id=youtube_id)],
        )

        # Add subtitles in whichever languages are available.
        for language in subtitle_languages:
            video_node.add_file(LanguagePatchedYouTubeSubtitleFile(
                youtube_id=youtube_id, youtube_language=language))

        return video_node

    img = doc.select_one(".uncode-single-media-wrapper img")
    if img:
        img_src = img["data-guid"] or img["src"]
        destination = tempfile.mkdtemp()
        download_file(img_src, destination, request_fn=make_request, filename="image.jpg")

        with open(os.path.join(destination, "index.html"), "w") as f:
            f.write("""
                <!doctype html>
                <html>
                <head></head>
                <body>
                    <img src="image.jpg" style="width: 100%; max-width: 1200px;" />
                </body>
                </html>
            """)

        zip_path = create_predictable_zip(destination)

        return nodes.HTML5AppNode(
            **base_node_attributes,
            files=[files.HTMLZipFile(zip_path)],
        )

    return None


_STRIP_ENGLISH_RE = re.compile("English (About|More Info|Transcript):.*", re.DOTALL)

def _strip_english(text):
    return _STRIP_ENGLISH_RE.sub('', text)


def create_description(doc):
    about = _strip_english(doc.select_one("#tab-about").text).strip()
    transcript = _strip_english(doc.select_one("#tab-transcript").text).strip()
    more_info = _strip_english(doc.select_one("#tab-more-info").text).strip()

    nav_tabs = doc.select_one(".tab-container .nav-tabs")
    tab_titles = [tab.text.strip() for tab in nav_tabs.children]

    description = about

    if transcript:
        description += "\n\n%s: %s" % (tab_titles[1].upper(), transcript)

    if more_info:
        description += "\n\n%s: %s" % (tab_titles[2].upper(), more_info)

    # Replace TE's unicode apostrophes that don't seem to show up in HTML with
    # the unicode "RIGHT SINGLE QUOTATION MARK".
    description = description.replace("\x92", "\u2019")

    return description


# From https://stackoverflow.com/a/7936523
def get_youtube_id_from_url(value):
    """
    Examples:
    - http://youtu.be/SA2iWivDJiE
    - http://www.youtube.com/watch?v=_oPAwA_Udwc&feature=feedu
    - http://www.youtube.com/embed/SA2iWivDJiE
    - http://www.youtube.com/v/SA2iWivDJiE?version=3&amp;hl=en_US
    """
    query = urlparse(value)
    if query.hostname == 'youtu.be':
        return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            return p['v'][0]
        if query.path[:7] == '/embed/':
            return query.path.split('/')[2]
        if query.path[:3] == '/v/':
            return query.path.split('/')[2]
    # fail?
    return None


# This is taken and modified from https://github.com/fle-internal/sushi-chef-ck12/blob/cb0d538b6857f399271d0895967727f635e58ee0/chef.py#L85
# TODO(davidhu): Extract to a util library
def make_request(url, clear_cookies=True, timeout=60, *args, **kwargs):
    if clear_cookies:
        sess.cookies.clear()

    # resolve ".." and "." references in url path to ensure cloudfront doesn't barf
    purl = urlparse(url)
    newpath = urllib.parse.urljoin(purl.path + "/", ".").rstrip("/")
    url = purl._replace(path=newpath).geturl()

    retry_count = 0
    max_retries = 5
    while True:
        try:
            response = sess.get(url, timeout=timeout, *args, **kwargs)
            break
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as e:
            retry_count += 1
            print("Error with connection ('{msg}'); about to perform retry {count} of {trymax}."
                  .format(msg=str(e), count=retry_count, trymax=max_retries))
            time.sleep(retry_count * 1)
            if retry_count >= max_retries:
                return Dummy404ResponseObject(url=url)

    if response.status_code != 200:
        print("NOT FOUND:", url)
        return None

    return response


def get_parsed_html_from_url(url, *args, **kwargs):
    request = make_request(url, *args, **kwargs)
    if not request:
        return None

    html = request.content
    return BeautifulSoup(html, "html.parser")


if __name__ == '__main__':
    """
    This code will run when the sushi chef is called from the command line.
    """
    print("----- Scraping Touchable Earth English channel! -----\n\n")
    EnglishChef().main()

    print("----- Scraping Touchable Earth French channel! -----\n\n")
    FrenchChef().main()
