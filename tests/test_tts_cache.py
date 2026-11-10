import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from scripts.tts_cache import AudioCache,key_for


class CacheTests(unittest.TestCase):
    def test_key_separates_reference_content_even_when_size_and_timestamp_equal(self):
        voice={'id':'a','audio_sha256':'hash-a','text_sha256':'text-a'}
        request={'text':'话术','speed':1.0,'language':'zh-CN'}
        first=key_for('engine-a',voice,request)
        for other in ({**voice,'audio_sha256':'hash-b'},{**voice,'text_sha256':'text-b'},{**voice,'id':'b'}):
            self.assertNotEqual(first,key_for('engine-a',other,request))
        self.assertNotEqual(first,key_for('engine-b',voice,request))
        for field,value in [('text','新话术'),('speed',1.5),('language','en-US')]:
            self.assertNotEqual(first,key_for('engine-a',voice,{**request,field:value}))

    def test_tampered_audio_missing_and_bad_metadata_are_cache_misses(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.wav';source.write_bytes(b'original')
            cache=AudioCache(root/'cache');key='a'*64;cache.put(key,source)
            audio,meta=cache.paths(key);self.assertEqual(cache.get(key),audio)
            stamp=audio.stat();audio.write_bytes(b'changed!');os.utime(audio,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            self.assertIsNone(cache.get(key))
            cache.put(key,source);meta.write_text('{broken',encoding='utf-8');self.assertIsNone(cache.get(key))
            cache.put(key,source);audio.unlink();self.assertIsNone(cache.get(key))
            with self.assertRaises(ValueError): cache.get('../escape')

    def test_cache_budget_only_evicts_owned_cache_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.wav';source.write_bytes(b'12345678')
            cache=AudioCache(root/'cache',max_entries=1,max_bytes=32)
            unrelated=cache.root/'operator-notes.txt';unrelated.write_text('keep')
            cache.put('a'*64,source);cache.put('b'*64,source)
            self.assertIsNone(cache.get('a'*64));self.assertIsNotNone(cache.get('b'*64))
            self.assertEqual(unrelated.read_text(),'keep');self.assertEqual(source.read_bytes(),b'12345678')


if __name__=='__main__': unittest.main()
