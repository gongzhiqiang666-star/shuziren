import json
from pathlib import Path
import tempfile
import unittest

from scripts.model_identity import build,load,manifest_path,verify


class ModelIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        model=self.root/'_internal/assets/pretrained_models/indextts';model.mkdir(parents=True)
        (model/'config.yaml').write_text('version: fixture\n',encoding='utf-8')
        (model/'gpt.pth').write_bytes(b'fixture-weight')
        (model/'._gpt.pth').write_bytes(b'macos-metadata')

    def test_build_load_verify_and_tamper(self):
        manifest=build(self.root,'indextts','open_source','fixture-license')
        self.assertEqual(len(manifest['files']),2)
        loaded=load(self.root,'indextts')
        self.assertEqual(loaded['license'],{'status':'open_source','reference':'fixture-license'})
        self.assertTrue(verify(self.root,'indextts')['verified'])
        (self.root/'_internal/assets/pretrained_models/indextts/gpt.pth').write_bytes(b'changed')
        result=verify(self.root,'indextts')
        self.assertFalse(result['verified'])
        self.assertEqual(result['mismatches'],['_internal/assets/pretrained_models/indextts/gpt.pth'])

    def test_manifest_tamper_and_invalid_license_rejected(self):
        with self.assertRaises(ValueError): build(self.root,'indextts','invented')
        build(self.root,'indextts')
        path=manifest_path(self.root,'indextts');value=json.loads(path.read_text(encoding='utf-8'))
        value['aggregate_sha256']='0'*64;path.write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaises(ValueError): load(self.root,'indextts')
        build(self.root,'indextts');value=json.loads(path.read_text(encoding='utf-8'))
        value['files'][0]['path']='../../outside.pth'
        value['aggregate_sha256']=__import__('hashlib').sha256(
            json.dumps(value['files'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        path.write_text(json.dumps(value),encoding='utf-8')
        with self.assertRaises(ValueError): load(self.root,'indextts')


if __name__=='__main__': unittest.main()
