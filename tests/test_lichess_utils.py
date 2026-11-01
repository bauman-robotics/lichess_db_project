"""
Тесты утилит Lichess: нормализация имени/URL и категории контроля.
Запуск: python -m unittest tests.test_lichess_utils
"""
import unittest

from core.utils.lichess import (
    LichessUsernameError,
    classify_time_control,
    normalize_lichess_username,
    player_table_name,
    safe_filename_part,
)


class NormalizeUsernameTests(unittest.TestCase):
    def test_plain_username(self):
        self.assertEqual(normalize_lichess_username("DenNedelin"), "DenNedelin")

    def test_at_prefix(self):
        self.assertEqual(normalize_lichess_username("@DenNedelin"), "DenNedelin")

    def test_https_profile(self):
        self.assertEqual(
            normalize_lichess_username("https://lichess.org/@/DenNedelin"),
            "DenNedelin",
        )

    def test_http_profile_with_slash_and_query(self):
        self.assertEqual(
            normalize_lichess_username("http://lichess.org/@/DenNedelin/?tab=games"),
            "DenNedelin",
        )

    def test_profile_without_scheme(self):
        self.assertEqual(
            normalize_lichess_username("lichess.org/@/DenNedelin"),
            "DenNedelin",
        )

    def test_www_host(self):
        self.assertEqual(
            normalize_lichess_username("https://www.lichess.org/@/DenNedelin"),
            "DenNedelin",
        )

    def test_whitespace(self):
        self.assertEqual(normalize_lichess_username("  @DenNedelin  "), "DenNedelin")

    def test_foreign_host_rejected(self):
        with self.assertRaises(LichessUsernameError):
            normalize_lichess_username("https://example.com/@/DenNedelin")

    def test_non_profile_path_rejected(self):
        with self.assertRaises(LichessUsernameError):
            normalize_lichess_username("https://lichess.org/training/123")

    def test_invalid_chars_rejected(self):
        with self.assertRaises(LichessUsernameError):
            normalize_lichess_username("Den Nedelin")
        with self.assertRaises(LichessUsernameError):
            normalize_lichess_username("Den/Nedelin")

    def test_empty_rejected(self):
        with self.assertRaises(LichessUsernameError):
            normalize_lichess_username("   ")


class TableNameTests(unittest.TestCase):
    def test_hyphen_and_case(self):
        self.assertEqual(player_table_name("Den-Nedelin"), "games_den_nedelin")

    def test_special_chars(self):
        self.assertEqual(player_table_name("a/b@c"), "games_a_b_c")

    def test_length_limit(self):
        self.assertLessEqual(len(player_table_name("x" * 100)), 63)

    def test_filename_part(self):
        self.assertEqual(safe_filename_part("a/b:c"), "a_b_c")


class TimeControlTests(unittest.TestCase):
    def test_blitz(self):
        self.assertEqual(classify_time_control("300+3"), "blitz")

    def test_rapid(self):
        self.assertEqual(classify_time_control("900+10"), "rapid")

    def test_bullet(self):
        self.assertEqual(classify_time_control("60+0"), "bullet")

    def test_classical(self):
        self.assertEqual(classify_time_control("1800+0"), "classical")

    def test_correspondence(self):
        self.assertEqual(classify_time_control("-"), "correspondence")
        self.assertEqual(classify_time_control("1 day per move"), "correspondence")
        self.assertEqual(classify_time_control("2 days per move"), "correspondence")

    def test_other(self):
        self.assertEqual(classify_time_control(None), "other")
        self.assertEqual(classify_time_control(""), "other")
        self.assertEqual(classify_time_control("unknown"), "other")


if __name__ == "__main__":
    unittest.main()
