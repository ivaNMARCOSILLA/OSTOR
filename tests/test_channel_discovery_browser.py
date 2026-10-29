"""Anonymous discovery uses real counters and accent-insensitive suggestions."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=browser.new_page()
  channels=[{'id':'a'*32,'title':'Música cercana','username':'Artista','bio':'En directo','category':'musica','view_count':2},{'id':'b'*32,'title':'Juegos en vivo','username':'Jugador','bio':'Comunidad','category':'videojuegos','view_count':12}]
  page.route('**/api/live/catalogue',lambda r:r.fulfill(json={'video_ready':True,'channels':channels}))
  page.route('**/api/status',lambda r:r.fulfill(json={'live_premiere':False,'maintenance':{'scope':'off'}}))
  page.goto(BASE_URL+'/live');page.locator('.live-channel').first.wait_for()
  assert page.locator('.live-channel h3').first.inner_text()=='Juegos en vivo'
  assert not page.evaluate('window.MaggySession.authenticated')
  page.locator('#channel-filter').fill('musica');assert page.locator('.live-channel').count()==1
  assert page.locator('#channel-suggestions option').first.get_attribute('value')=='Música cercana'
  page.locator('#channel-filter').fill('art');assert page.locator('.live-channel h3').inner_text()=='Música cercana'
  browser.close()
 print('OK: anonymous popular channels and letter matching without accent sensitivity')
if __name__=='__main__':run()
