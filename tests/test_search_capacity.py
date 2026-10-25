"""Large result sets retain paging, access filters and provider independence."""
import unittest
from unittest.mock import patch
import app

class SearchCapacityTests(unittest.TestCase):
    @patch.object(app, 'fetch_json')
    def test_archive_returns_sixty_unique_candidates_without_metadata_fetches(self, fetch):
        fetch.return_value={'response':{'docs':[{'identifier':f'piano_{i}','title':f'Piano {i}'} for i in range(60)]}}
        tracks=app.search_archive('piano',limit=60,page=2)
        self.assertEqual(len(tracks),60)
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(fetch.call_args.args[1]['rows'],60)
        self.assertEqual(fetch.call_args.args[1]['page'],2)

    @patch.object(app, 'fetch_json')
    def test_audius_later_pages_use_offset_and_keep_access_filter(self, fetch):
        fetch.return_value={'data':[{'id':f'p{i}','title':'Piano'} for i in range(59)]+[{'id':'gated','is_stream_gated':True}]}
        tracks=app.search_audius('piano',limit=60,page=3)
        self.assertEqual(len(tracks),59)
        self.assertEqual(fetch.call_args.args[1]['offset'],120)
        self.assertEqual(fetch.call_args.args[1]['limit'],60)
        self.assertNotIn('audius_gated',[t['id'] for t in tracks])

    @patch.object(app,'search_archive')
    @patch.object(app,'search_audius')
    def test_combined_page_can_return_120_real_unique_results(self,audius,archive):
        app._search_cache.clear()
        audius.return_value=[{'id':f'audius_{i}','title':'Piano','source':'AUDIUS'} for i in range(60)]
        archive.return_value=[{'id':f'archive_{i}','title':'Piano','source':'ARCHIVE'} for i in range(60)]
        tracks=app.multi_search('piano',page=2)
        self.assertEqual(len(tracks),120)
        self.assertEqual(len({t['id'] for t in tracks}),120)
        audius.assert_called_once_with('piano',60,page=2)
        archive.assert_called_once_with('piano',60,page=2)
