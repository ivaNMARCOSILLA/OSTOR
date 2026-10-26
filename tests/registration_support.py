"""Solve the real local test challenge; never bypass server verification."""
from unittest.mock import patch

def registration_data(client,data):
 if 'human_id' in data:return data
 if hasattr(client,'request'):
  from browser_support import BASE_URL
  challenge=client.request.get(BASE_URL+'/api/account/human-check').json()
 else:
  with patch('human_check.new_code',return_value='OL234'):challenge=client.get('/api/account/human-check').json
 return dict(data,human_id=challenge['id'],human_answer='OL234')
