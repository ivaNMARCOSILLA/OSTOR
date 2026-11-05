"""Search discovery contains real public canonical pages and the brand photograph."""
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import unittest
import xml.etree.ElementTree as ET

import app
from auth_support import authenticated_client


NS={'s':'http://www.sitemaps.org/schemas/sitemap/0.9',
    'image':'http://www.google.com/schemas/sitemap-image/1.1'}
ORIGIN='https://electronicama.com'


class SearchHead(HTMLParser):
 def __init__(self,source):
  super().__init__();self.canonical=None;self.robots='';self.feed(source)
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='link' and attrs.get('rel')=='canonical':self.canonical=attrs.get('href')
  if tag=='meta' and attrs.get('name')=='robots':self.robots=attrs.get('content','').lower()


class SitemapTests(unittest.TestCase):
 def setUp(self):
  authenticated_client(app.app,self.addCleanup)
  self.client=app.app.test_client()  # Discovery must also work without a session.

 def sitemap(self):
  with self.client.get('/sitemap.xml') as response:
   self.assertEqual(response.status_code,200)
   self.assertEqual(response.mimetype,'application/xml')
   return ET.fromstring(response.data)

 def test_canonical_public_pages_are_indexable_and_not_internal_or_fragment_urls(self):
  root=self.sitemap()
  locations=[node.text for node in root.findall('s:url/s:loc',NS)]
  self.assertEqual(len(locations),len(set(locations)))
  self.assertIn(ORIGIN+'/',locations);self.assertIn(ORIGIN+'/live',locations)
  self.assertEqual(len(locations),5)
  for location in locations:
   url=urlsplit(location)
   self.assertEqual((url.scheme,url.netloc),('https','electronicama.com'))
   self.assertFalse(url.query or url.fragment)
   self.assertFalse(url.path.startswith(('/api/','/account','/streamers')))
   with self.client.get(url.path) as response:
    self.assertEqual(response.status_code,200,location)
    self.assertEqual(response.mimetype,'text/html')
    head=SearchHead(response.get_data(as_text=True))
    self.assertEqual(head.canonical,location)
    self.assertNotIn('noindex',head.robots)
   self.assertIsNone(root.find('s:url/s:lastmod',NS))

 def test_home_image_in_sitemap_is_public_raster_and_alias_uses_live_canonical(self):
  root=self.sitemap()
  home=next(node for node in root.findall('s:url',NS) if node.find('s:loc',NS).text==ORIGIN+'/')
  image=home.find('image:image/image:loc',NS).text
  url=urlsplit(image)
  self.assertEqual(url.netloc,'electronicama.com')
  with self.client.get(url.path) as response:
   self.assertEqual(response.status_code,200)
   self.assertEqual(response.mimetype,'image/png')
   self.assertTrue(response.data.startswith(b'\x89PNG\r\n\x1a\n'))
  with self.client.get('/streamers') as response:
   self.assertEqual(response.status_code,200)
   self.assertEqual(SearchHead(response.get_data(as_text=True)).canonical,ORIGIN+'/live')

 def test_robots_advertises_sitemap_and_allows_image_and_noindex_page_discovery(self):
  with self.client.get('/robots.txt') as response:
   self.assertEqual(response.status_code,200)
   self.assertEqual(response.mimetype,'text/plain')
   rules=RobotFileParser();rules.parse(response.get_data(as_text=True).splitlines())
  self.assertEqual(rules.site_maps(),[ORIGIN+'/sitemap.xml'])
  for path in ['/','/live','/account','/assets/electronicama-social.png','/sitemap.xml']:
   self.assertTrue(rules.can_fetch('Googlebot',ORIGIN+path),path)
  self.assertFalse(rules.can_fetch('Googlebot',ORIGIN+'/api/admin/members'))


if __name__=='__main__':unittest.main()
