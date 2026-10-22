import html
import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from tracker.services.steam_api import fetch_app_news


class SteamNewsApiTests(SimpleTestCase):
    @override_settings(STEAM_THROTTLE_SECONDS=0)
    @patch("tracker.services.steam_api.requests.get")
    def test_fetch_app_news_attaches_event_capsule_image(self, get):
        api_response = Mock(
            status_code=200,
            json=lambda: {
                "appnews": {
                    "newsitems": [
                        {
                            "gid": "1846651706694551",
                            "title": "REDstreams",
                            "contents": "Announcement body",
                        },
                    ],
                },
            },
        )
        event_metadata = [
            {
                "event_name": "REDstreams",
                "clan_steamid": "103582791464731680",
                "jsondata": json.dumps({
                    "localized_capsule_image": [
                        "12c97f011ba5d07c05359e8e39e86751a009650d.png",
                    ],
                }),
            },
        ]
        community_response = Mock(
            status_code=200,
            text=(
                '<div data-partnereventstore="'
                f'{html.escape(json.dumps(event_metadata), quote=True)}'
                '"></div>'
            ),
        )
        get.side_effect = [api_response, community_response]

        items = fetch_app_news(1091500)

        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0].cover_image,
            "https://clan.akamai.steamstatic.com/images/"
            "35210272/12c97f011ba5d07c05359e8e39e86751a009650d.png",
        )
