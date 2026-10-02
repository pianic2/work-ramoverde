"""WR-14 guard: mobile credentials live only in Expo SecureStore behind the auth boundary."""

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MOBILE = REPO / "apps" / "mobile"


def mobile_sources() -> list[Path]:
    return sorted(
        path
        for folder in (MOBILE / "app", MOBILE / "src")
        for path in folder.rglob("*")
        if path.suffix in {".ts", ".tsx", ".js"}
    )


class MobileSecretStorageTests(unittest.TestCase):
    def test_no_async_storage_or_web_storage(self):
        for path in mobile_sources():
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(REPO))):
                self.assertNotRegex(text, r"async-storage|AsyncStorage")
                self.assertNotRegex(text, r"localStorage|sessionStorage")

    def test_secure_store_is_used_only_by_auth_boundary_and_theme_adapter(self):
        users = sorted(
            str(path.relative_to(MOBILE))
            for path in mobile_sources()
            if "expo-secure-store" in path.read_text(encoding="utf-8")
        )
        self.assertEqual(users, ["src/auth/tokens.ts", "src/theme-storage.ts"])

    def test_only_the_public_api_url_is_an_expo_public_variable(self):
        texts = [path.read_text(encoding="utf-8") for path in mobile_sources()]
        texts.append((REPO / ".env.example").read_text(encoding="utf-8"))
        texts.append((MOBILE / "app.json").read_text(encoding="utf-8"))
        names = {name for text in texts for name in re.findall(r"EXPO_PUBLIC_[A-Z0-9_]+", text)}
        self.assertEqual(names, {"EXPO_PUBLIC_API_URL"})


if __name__ == "__main__":
    unittest.main()
