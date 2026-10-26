"""Check the real 1000-sticker collection and its short original sound signatures."""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import wave
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sounds import sound_bytes
from sticker_phrases import phrase_for

records=json.loads((ROOT/'assets/stickers/catalogue.json').read_text());packs=json.loads((ROOT/'assets/stickers/sheets/index.json').read_text())
assert len(records)==999 and len(packs)==11
assert len({item['id'] for item in records})==999
assert len({item['image'] for item in records})==999
assert sum(pack['count'] for pack in packs)==999
seen_images=set();seen_sounds=set();seen_phrases=set();size=0
for index,record in enumerate([{'id':'hello','image':'/assets/stickers/creator.webp'}]+records):
 path=ROOT/record['image'].lstrip('/');assert path.is_file(),path
 size+=path.stat().st_size
 with Image.open(path) as original:
  image=original.convert('RGBA');assert max(image.size)<=256;assert image.getchannel('A').getextrema()[0]==0
  digest=hashlib.sha256(image.tobytes()).digest();assert digest not in seen_images;seen_images.add(digest)
 phrase=phrase_for(record['id']);assert phrase not in seen_phrases;seen_phrases.add(phrase)
 sound=sound_bytes('sticker:'+record['id']);digest=hashlib.sha256(sound).digest();assert digest not in seen_sounds;seen_sounds.add(digest)
 with wave.open(io.BytesIO(sound)) as audio:
  assert audio.getnchannels()==1 and audio.getsampwidth()==2
  assert 0.5<=audio.getnframes()/audio.getframerate()<=1
  pcm=audio.readframes(audio.getnframes());peak=max(abs(value) for value, in struct.iter_unpack('<h',pcm));assert 100<peak<=11000
 if (index+1)%100==0:print(json.dumps({'verified_images_and_sounds':index+1}),flush=True)
for pack in packs:assert (ROOT/pack['image'].lstrip('/')).is_file()
print(json.dumps({'stickers':len(seen_images),'unique_sounds':len(seen_sounds),'unique_phrases':len(seen_phrases),'sheets':len(packs),'image_bytes':size,'creator_number_one_free':True}))
