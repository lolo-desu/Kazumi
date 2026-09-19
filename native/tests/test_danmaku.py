from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nativeapp.danmaku import Comment, parse_comments, schedule


class DanmakuTests(unittest.TestCase):
    def test_json_and_xml_keep_timing_color_and_mode(self):
        json = '{"comments":[{"p":"1.25,5,1122867,user","m":"测试"}]}'
        xml = '<i><d p="1.25,5,25,1122867,0,0,0,0">测试</d></i>'
        self.assertEqual(parse_comments(json), parse_comments(xml))
        self.assertEqual(parse_comments(xml)[0], Comment(1.25, "测试", 5, 0x112233))

    def test_xml_entities_are_rejected(self):
        with self.assertRaises(ValueError):
            parse_comments('<!DOCTYPE i [<!ENTITY a "test">]><i/>')

    def test_lanes_do_not_allow_fast_long_comment_to_catch_previous(self):
        comments = [Comment(0, "short"), Comment(0.1, "long"), Comment(7, "long")]
        widths = {"short": 100, "long": 800}
        result = schedule(comments, 1000, 1, widths.__getitem__)
        self.assertEqual([comment.time for comment, _, _ in result], [0, 7])

    def test_blocklist_and_fixed_comments(self):
        result = schedule(
            [Comment(0, "skip"), Comment(1, "top", 5), Comment(2, "bottom", 4)],
            1000,
            2,
            lambda _: 100,
            blocked=["skip"],
        )
        self.assertEqual([comment.text for comment, _, _ in result], ["top", "bottom"])


if __name__ == "__main__":
    unittest.main()
