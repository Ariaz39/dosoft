import unittest

from retro_notification_engine import parse_retro_notification


class RetroNotificationTests(unittest.TestCase):
    def test_trade_is_recognized_in_french(self):
        event = parse_retro_notification([
            "Joueur-test - Dofus Retro v1.49.5",
            "Un aventurier vous propose un échange.",
        ])
        self.assertEqual(event["event_type"], "trade")
        self.assertEqual(event["pseudo"], "Joueur-test")
        self.assertEqual(event["locale"], "fr")

    def test_group_is_recognized_in_english(self):
        event = parse_retro_notification([
            "Player - Dofus Retro",
            "Friend invites you to join their group",
        ])
        self.assertEqual(event["event_type"], "group")
        self.assertEqual(event["locale"], "en")

    def test_unrelated_notification_is_ignored(self):
        self.assertIsNone(parse_retro_notification(["Mail", "Nouveau message"]))


if __name__ == "__main__":
    unittest.main()
