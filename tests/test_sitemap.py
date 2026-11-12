"""Search discovery contains real public canonical pages and the brand photograph."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from unittest.mock import patch
import re
import unittest
import xml.etree.ElementTree as ET

import app
from auth_support import authenticated_client


NS={'s':'http://www.sitemaps.org/schemas/sitemap/0.9',
    'image':'http://www.google.com/schemas/sitemap-image/1.1'}
ORIGIN='https://electronicama.com'


def google_resource_allowed(source,url):
 """Evaluate Google's path wildcards, end anchors and longest matching rule.

 This test helper intentionally accepts only the single universal group shipped
 by this site. urllib.robotparser treats '$' literally and uses first-match
 ordering, so it cannot check these renderer exceptions accurately.
 """
 parsed=urlsplit(url)
 target=parsed.path+('?' + parsed.query if parsed.query else '')
 matches=[];agents=[]
 for line in source.splitlines():
  line=line.split('#',1)[0].strip()
  if not line or ':' not in line:continue
  key,pattern=[value.strip() for value in line.split(':',1)]
  key=key.lower()
  if key=='user-agent':agents.append(pattern)
  if key not in {'allow','disallow'} or not pattern:continue
  anchored=pattern.endswith('$')
  path=pattern[:-1] if anchored else pattern
  expression='^'+re.escape(path).replace(r'\*','.*')+('$' if anchored else '')
  if re.match(expression,target):matches.append((len(pattern.encode('utf-8')),key=='allow'))
 if agents!=['*']:raise AssertionError('Update the helper if crawler-specific groups are introduced.')
 return max(matches)[1] if matches else True


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
  self.assertEqual(len(locations),6)
  self.assertIn(ORIGIN+'/videos',locations)
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

 def test_google_resource_rules_use_specificity_anchors_and_query_separator(self):
  # Policy order must not determine the outcome; '?' is a literal URL query
  # separator, '*' is a wildcard and '$' requires the entire path to match.
  source='''User-agent: *
Disallow: /api/
Allow: /api/search?
Allow: /api/status$
Disallow: /api/search?private=
Allow: /assets/*.js$
Disallow: /assets/
'''
  for path in ['/api/search?q=music','/api/status','/assets/mobile-shell.js']:
   self.assertTrue(google_resource_allowed(source,ORIGIN+path),path)
  for path in ['/api/search-private','/api/search?private=1','/api/status/private',
               '/api/status?private=1','/assets/private.txt']:
   self.assertFalse(google_resource_allowed(source,ORIGIN+path),path)
  tie='User-agent: *\nDisallow: /api/status$\nAllow: /api/status$\n'
  self.assertTrue(google_resource_allowed(tie,ORIGIN+'/api/status'))

 def test_google_can_render_public_content_without_crawling_private_or_live_state(self):
  with self.client.get('/robots.txt') as response:source=response.get_data(as_text=True)
  allowed=['/api/locale','/api/status','/api/search',
   '/api/search?q=electronic%20music&page=1&source=ARCHIVE',
   '/api/search?q=electronic%20music&page=1&source=AUDIUS',
   '/assets/electronicama-social.png','/assets/mobile-shell.js?v=9.29.5']
  blocked=['/api/account/me','/api/account/me?preview=1','/api/admin/members',
   '/api/payments/status','/api/payments/checkout','/api/sync',
   '/api/visits/public?compact=1','/api/stickers/voices',
   '/api/search-private','/api/search/private','/api/searching?q=music',
   '/api/locale-private','/api/locale/private','/api/locale?preview=1',
   '/api/status-private','/api/status/private','/api/status?preview=1']
  for path in allowed:
   self.assertTrue(google_resource_allowed(source,ORIGIN+path),path)
  for path in blocked:
   self.assertFalse(google_resource_allowed(source,ORIGIN+path),path)

 def test_public_rendering_reads_work_without_login_and_api_json_is_not_indexed(self):
  with patch.object(app,'rate_allowed',return_value=True),patch.object(app,'multi_search',return_value=[{
   'id':'archive_public-fixture','source':'ARCHIVE','title':'Public music fixture','channel':'Public artist'
  }]) as search:
   for provider in ['ARCHIVE','AUDIUS']:
    path='/api/search?q=electronic%20music&page=1&source='+provider
    with self.client.get(path) as response:
     self.assertEqual(response.status_code,200)
     self.assertEqual(response.mimetype,'application/json')
     self.assertEqual(response.json[0]['title'],'Public music fixture')
     self.assertEqual(response.headers.get('X-Robots-Tag'),'noindex')
    search.assert_called_with('electronic music',page=1,source=provider)
  for path in ['/api/locale','/api/status','/api/account/me','/api/admin/members','/api/stickers/voices']:
   with self.client.get(path) as response:
    self.assertEqual(response.headers.get('X-Robots-Tag'),'noindex',path)
    self.assertEqual(response.status_code,{'/api/admin/members':403,'/api/stickers/voices':401}.get(path,200),path)
    if path=='/api/account/me':self.assertIsNone(response.json['user'])

 def test_mobile_script_and_brand_image_are_public_assets_without_noindex(self):
  for path,mimetypes in [('/assets/mobile-shell.js?v=9.29.5',{'text/javascript','application/javascript'}),
                         ('/assets/electronicama-social.png',{'image/png'})]:
   with self.client.get(path) as response:
    self.assertEqual(response.status_code,200,path)
    self.assertIn(response.mimetype,mimetypes,path)
    self.assertNotIn('X-Robots-Tag',response.headers,path)
    self.assertEqual(response.data,Path(app.ROOT,urlsplit(path).path.lstrip('/')).read_bytes())


if __name__=='__main__':unittest.main()
