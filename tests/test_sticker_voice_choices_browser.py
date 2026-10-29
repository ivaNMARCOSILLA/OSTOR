"""Distinct stable scenes and actual installed female/male voice selection, without external synthesis."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context();login_context(ctx);page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.add_init_script("""window.spoken=[];window.SpeechSynthesisUtterance=class{constructor(text){this.text=text}};speechSynthesis.getVoices=()=>[{name:'Microsoft Elvira',voiceURI:'elvira',lang:'es-ES',localService:true},{name:'Microsoft Alvaro',voiceURI:'alvaro',lang:'es-ES',localService:true}];speechSynthesis.speak=s=>spoken.push({text:s.text,voice:s.voice?.voiceURI,pitch:s.pitch});speechSynthesis.cancel=()=>{};""")
  page.goto(BASE_URL+'/account#ol-collection');page.locator('.collection-sticker').first.wait_for()
  scenes=page.locator('.collection-sticker').evaluate_all("els=>els.map(e=>e.style.getPropertyValue('--sticker-scene'))")
  assert len(set(scenes))==len(scenes) and all(scenes)
  assert page.evaluate('spoken.length')==0
  page.locator('[data-voice-profile]').select_option('male');page.locator('.sticker-sound-button').first.click()
  page.wait_for_function("spoken.length===1");assert page.evaluate('spoken[0].voice')=='alvaro';assert page.evaluate('spoken[0].pitch')==1
  page.locator('[data-voice-profile]').select_option('female');page.locator('.sticker-sound-button').first.click()
  page.wait_for_function('spoken.length===2');assert page.evaluate('spoken[1].voice')=='elvira'
  page.locator('[data-voice-profile]').select_option('male');page.reload();page.locator('.collection-sticker').first.wait_for()
  assert page.locator('[data-voice-profile]').input_value()=='male'
  assert page.evaluate('spoken.length')==0
  page.wait_for_function("document.querySelector('[data-voice-engine] option[value=neural]').disabled")
  assert 'pendiente' in page.locator('[data-voice-status]').inner_text()
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: unique stable backgrounds, explicit male/female real installed voices, unchanged pitch, saved preference, no autoplay, neural configuration honestly pending')
if __name__=='__main__':run()
