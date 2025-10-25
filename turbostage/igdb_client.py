import json
from datetime import datetime
from typing import Any

import requests
from igdb.wrapper import IGDBWrapper

from turbostage.constants import IGDB_CLIENT_ID, IGDB_CLIENT_SECRET, IGDB_DOS_PLATFORM_ID

# API documentation: https://api-docs.igdb.com/#authentication


class IgdbClient:
    def __init__(self):
        self._auth_token = self._get_auth()
        self._wrapper = IGDBWrapper(IGDB_CLIENT_ID, self._auth_token)

    @staticmethod
    def _get_auth() -> str:
        request_url = (
            f"https://id.twitch.tv/oauth2/token?client_id={IGDB_CLIENT_ID}"
            f"&client_secret={IGDB_CLIENT_SECRET}&grant_type=client_credentials"
        )
        response = requests.post(request_url)
        response.raise_for_status()  # A better way to handle HTTP errors
        return response.json()["access_token"]

    def _format_image_url(self, image_hash: str, size: str = "t_cover_big") -> str:
        """Constructs a full image URL from an IGDB image hash."""
        return f"https://images.igdb.com/igdb/image/upload/{size}/{image_hash}.jpg"

    def search_games(self, search_query: str) -> list[dict[str, Any]]:
        """Searches for games and returns a list of basic info."""
        query = f"""
        search "{search_query}";
        fields name;
        where platforms = ({IGDB_DOS_PLATFORM_ID});
        limit 20;
        """
        byte_array = self._wrapper.api_request("games", query)
        return json.loads(byte_array)

    def get_game_info(self, igdb_id: int) -> dict[str, Any] | None:
        """
        Fetches all necessary game details in a single, efficient API call.
        """
        # This single query fetches the game and all related (nested) data.
        query = f"""
        fields
            name,
            summary,
            aggregated_rating,
            cover.image_id,
            genres.name,
            screenshots.image_id,
            involved_companies.publisher,
            involved_companies.developer,
            involved_companies.company.name,
            release_dates.date,
            release_dates.platform;
        where id = {igdb_id};
        """
        byte_array = self._wrapper.api_request("games", query)
        results = json.loads(byte_array)

        if not results:
            return None

        game_data = results[0]

        # --- Process the API data into a clean dictionary ---

        # Developers and Publishers
        developers = []
        publishers = []
        if "involved_companies" in game_data:
            for company in game_data["involved_companies"]:
                # The company data might not always be present
                if "company" in company and "name" in company["company"]:
                    if company.get("developer"):
                        developers.append(company["company"]["name"])
                    if company.get("publisher"):
                        publishers.append(company["company"]["name"])

        # Release Date
        release_date = None
        if "release_dates" in game_data:
            dos_release = next(
                (rd for rd in game_data["release_dates"] if rd["platform"] == IGDB_DOS_PLATFORM_ID), None
            )
            # Fallback to the first release date if no specific DOS date is found
            chosen_release = dos_release or game_data["release_dates"][0]
            if "date" in chosen_release:
                release_date = chosen_release["date"]

        # Cover URL
        cover_url = ""
        if "cover" in game_data and "image_id" in game_data["cover"]:
            cover_url = self._format_image_url(game_data["cover"]["image_id"], "t_cover_big")

        # Screenshot URLs
        screenshot_urls = []
        if "screenshots" in game_data:
            screenshot_urls = [
                self._format_image_url(s["image_id"], "t_screenshot_big") for s in game_data["screenshots"]
            ]

        # Assemble the final dictionary, matching the UI widget's needs
        return {
            "name": game_data.get("name"),
            "summary": game_data.get("summary", "No summary available."),
            "cover_url": cover_url,
            "release_date": release_date,
            "genres": [g["name"] for g in game_data.get("genres", [])],
            "publisher": ", ".join(publishers) or None,
            "developer": ", ".join(developers) or None,
            "rating": game_data.get("aggregated_rating"),
            "screenshot_urls": screenshot_urls,
        }
