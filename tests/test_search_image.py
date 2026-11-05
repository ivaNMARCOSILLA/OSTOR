"""Search and link previews refer to the same real, visible home-page image."""
from html.parser import HTMLParser
import json
from pathlib import Path
import struct
import unittest
from urllib.parse import urlsplit


ROOT=Path(__file__).resolve().parents[1]


class PageImages(HTMLParser):
 def __init__(self,source):
  super().__init__();self.meta={};self.images=[];self.schema=[];self._schema=None;self.feed(source)
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='meta':self.meta[attrs.get('property') or attrs.get('name')]=attrs.get('content')
  elif tag=='img':self.images.append(attrs)
  elif tag=='script' and attrs.get('type')=='application/ld+json':self._schema=''
 def handle_data(self,data):
  if self._schema is not None:self._schema+=data
 def handle_endtag(self,tag):
  if tag=='script' and self._schema is not None:
   self.schema.append(json.loads(self._schema));self._schema=None


class SearchImageTests(unittest.TestCase):
 def test_primary_image_is_a_real_raster_used_on_the_page_and_in_previews(self):
  page=PageImages((ROOT/'index.html').read_text())
  graph={node['@id']:node for schema in page.schema for node in schema.get('@graph',[])}
  webpage=next(node for node in graph.values() if node['@type']=='WebPage')
  image=graph[webpage['primaryImageOfPage']['@id']]
  self.assertEqual(image['@type'],'ImageObject')
  url=urlsplit(image['contentUrl'])
  self.assertEqual(url.scheme,'https');self.assertEqual(url.netloc,'electronicama.com')
  content=(ROOT/url.path.lstrip('/')).read_bytes()
  self.assertEqual(content[:8],b'\x89PNG\r\n\x1a\n')
  width,height=struct.unpack('>II',content[16:24])
  self.assertGreaterEqual(width,1200)
  self.assertEqual((image['width'],image['height']),(width,height))
  visible=next(item for item in page.images if urlsplit(item.get('src','')).path==url.path)
  self.assertTrue(visible['alt']);self.assertNotIn('hidden',visible)
  self.assertEqual((int(visible['width']),int(visible['height'])),(width,height))
  for key in ['og:image','og:image:secure_url','twitter:image']:
   self.assertEqual(page.meta[key],image['contentUrl'])
  self.assertEqual((int(page.meta['og:image:width']),int(page.meta['og:image:height'])),(width,height))
  self.assertEqual(page.meta['og:image:type'],'image/png')
  self.assertTrue(page.meta['twitter:image:alt'])
  self.assertIn('max-image-preview:large',page.meta['robots'])


if __name__=='__main__':unittest.main()
