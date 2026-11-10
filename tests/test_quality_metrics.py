"""Corpus/scoring/ROI checks; no inference or perceptual quality claim."""
import json
from pathlib import Path
import tempfile
import unittest
import cv2
import numpy as np

from scripts.quality_metrics import content_score,compare_videos,normalize


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.corpus=json.loads((Path(__file__).resolve().parents[1]/'scripts/fixtures/v04-quality-corpus.json').read_text(encoding='utf-8'))

    def test_fixed_50_cases_and_critical_tokens(self):
        items=self.corpus['items']
        self.assertEqual([item['id'] for item in items],[f'Q{i:03d}' for i in range(1,51)])
        self.assertTrue(all(item.get('required_tokens') for item in items[:30]))
        self.assertEqual([item['speed'] for item in items[40:46]],[.5,.75,1,1.25,1.5,2])

    def test_digits_equivalent_but_wrong_number_blocked_despite_low_cer(self):
        item=self.corpus['items'][0]
        self.assertTrue(content_score('测试容量是530毫升',item,.15)['passed'])
        wrong=content_score('测试容量是五百二十毫升',item,.15)
        self.assertLessEqual(wrong['cer'],.15);self.assertFalse(wrong['passed'])
        self.assertFalse(content_score('测试容量是1530毫升',item,.15)['passed'])

    def test_brand_and_negation_required(self):
        item=self.corpus['items'][14]
        self.assertFalse(content_score('这是美帝品牌名称的读音测试',item,.15)['passed'])
        negation=self.corpus['items'][48]
        self.assertFalse(content_score('请保留可以发货这句话，改成可以发货',negation,.15)['passed'])
        self.assertTrue(content_score(negation['expected'],negation,.15)['passed'])

    def test_mixed_case_spaces_and_punctuation(self):
        item=self.corpus['items'][25]
        self.assertTrue(content_score('这个名称读作 deep seek',item,.15)['passed'])
        self.assertEqual(normalize('０．７５',self.corpus['items'][2]),'零点七五')

    def test_roi_identical_different_and_missing_landmarks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);avatar=root/'avatar';(avatar/'frames').mkdir(parents=True);(avatar/'positions').mkdir()
            points=[[12,16]]*68
            for i in range(3):
                (avatar/'frames'/f'{i:06d}.jpg').touch()
                (avatar/'positions'/f'{i:06d}.txt').write_text('landmarks: '+repr(points)+'\n')
            paths=[]
            for name,color in [('a',100),('b',100),('c',130)]:
                path=root/(name+'.mp4');paths.append(path)
                writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),25,(24,32))
                self.assertTrue(writer.isOpened())
                for _ in range(3):writer.write(np.full((32,24,3),color,np.uint8))
                writer.release()
            self.assertTrue(compare_videos(paths[0],paths[1],avatar,self.corpus['thresholds'])['passed'])
            self.assertFalse(compare_videos(paths[0],paths[2],avatar,self.corpus['thresholds'])['passed'])
            for path in (avatar/'positions').glob('*.txt'):path.write_text('is_no_face: True\n')
            missing=compare_videos(paths[0],paths[1],avatar,self.corpus['thresholds'])
            self.assertEqual(missing['mouth_roi_coverage'],0);self.assertFalse(missing['passed'])


if __name__=='__main__':unittest.main()
