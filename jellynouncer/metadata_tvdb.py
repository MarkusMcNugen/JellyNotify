"""
TheTVDB API v4 integration module.

Standalone module for fetching TV metadata from TheTVDB API v4.
Requires only asyncio and aiohttp. No external dependencies on project files.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin

import aiohttp
from aiohttp import ClientTimeout, ClientSession, ClientError

logger = logging.getLogger(__name__)


# TVDB Data Models

@dataclass(slots=True)
class TVDBArtwork:
    """TVDB artwork metadata."""

    id: Optional[int] = None
    image: Optional[str] = None
    thumbnail: Optional[str] = None
    type: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    includes_text: Optional[bool] = None
    language: Optional[str] = None
    score: Optional[float] = None


@dataclass(slots=True)
class TVDBCharacter:
    """TVDB character information."""

    id: Optional[int] = None
    name: Optional[str] = None
    person_name: Optional[str] = None
    person_image: Optional[str] = None
    episode_id: Optional[int] = None
    series_id: Optional[int] = None
    movie_id: Optional[int] = None
    is_featured: Optional[bool] = None
    sort_order: Optional[int] = None
    role: Optional[str] = None


@dataclass(slots=True)
class TVDBCompany:
    """TVDB company/network information."""

    id: Optional[int] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    name_translations: List[str] = field(default_factory=list)
    overview_translations: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    country: Optional[str] = None
    primary_company_type: Optional[int] = None
    active_date: Optional[str] = None
    inactive_date: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass(slots=True)
class TVDBSeasonType:
    """TVDB season type information."""

    id: Optional[int] = None
    name: Optional[str] = None
    type: Optional[str] = None
    alt_name: Optional[str] = None


@dataclass(slots=True)
class TVDBRemoteId:
    """TVDB remote ID mappings."""

    id: Optional[str] = None
    type: Optional[int] = None
    source_name: Optional[str] = None


@dataclass(slots=True)
class TVDBSeriesMetadata:
    """TVDB series metadata."""

    tvdb_id: Optional[int] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    overview: Optional[str] = None
    original_country: Optional[str] = None
    original_language: Optional[str] = None
    default_season_type: Optional[int] = None
    status: Optional[str] = None
    first_aired: Optional[str] = None
    last_aired: Optional[str] = None
    next_aired: Optional[str] = None
    score: Optional[float] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    average_runtime: Optional[int] = None
    is_order_randomized: Optional[bool] = None
    name_translations: List[str] = field(default_factory=list)
    overview_translations: List[str] = field(default_factory=list)
    alias_translations: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    companies: List[TVDBCompany] = field(default_factory=list)
    characters: List[TVDBCharacter] = field(default_factory=list)
    artworks: List[TVDBArtwork] = field(default_factory=list)
    remote_ids: List[TVDBRemoteId] = field(default_factory=list)
    poster_url: Optional[str] = None
    banner_url: Optional[str] = None
    fanart_url: Optional[str] = None
    last_updated: Optional[str] = None
    year: Optional[str] = None


@dataclass(slots=True)
class TVDBSeasonMetadata:
    """TVDB season metadata."""

    tvdb_id: Optional[int] = None
    series_id: Optional[int] = None
    name: Optional[str] = None
    number: Optional[int] = None
    overview: Optional[str] = None
    image: Optional[str] = None
    image_type: Optional[int] = None
    year: Optional[str] = None
    season_type: Optional[TVDBSeasonType] = None
    name_translations: List[str] = field(default_factory=list)
    overview_translations: List[str] = field(default_factory=list)
    companies: List[TVDBCompany] = field(default_factory=list)
    artworks: List[TVDBArtwork] = field(default_factory=list)
    last_updated: Optional[str] = None


@dataclass(slots=True)
class TVDBEpisodeMetadata:
    """TVDB episode metadata."""

    tvdb_id: Optional[int] = None
    series_id: Optional[int] = None
    season_id: Optional[int] = None
    name: Optional[str] = None
    overview: Optional[str] = None
    image: Optional[str] = None
    image_type: Optional[int] = None
    number: Optional[int] = None
    absolute_number: Optional[int] = None
    season_number: Optional[int] = None
    aired_order: Optional[int] = None
    dvd_order: Optional[int] = None
    aired: Optional[str] = None
    runtime: Optional[int] = None
    production_code: Optional[str] = None
    finale_type: Optional[str] = None
    rating: Optional[float] = None
    rating_count: Optional[int] = None
    is_movie: Optional[bool] = None
    name_translations: List[str] = field(default_factory=list)
    overview_translations: List[str] = field(default_factory=list)
    characters: List[TVDBCharacter] = field(default_factory=list)
    artworks: List[TVDBArtwork] = field(default_factory=list)
    companies: List[TVDBCompany] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    nominations: List[Dict[str, Any]] = field(default_factory=list)
    last_updated: Optional[str] = None
    year: Optional[str] = None


# Exception Classes

class TVDBAPIError(Exception):
    """Base exception for TVDB API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class TVDBAuthenticationError(TVDBAPIError):
    """Authentication failed with TVDB API."""
    pass


class TVDBRateLimitError(TVDBAPIError):
    """Rate limit exceeded for TVDB API."""

    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after or 60


class TVDBNotFoundError(TVDBAPIError):
    """Requested resource not found in TVDB."""
    pass


class TVDBServerError(TVDBAPIError):
    """TVDB server error (5xx responses)."""
    pass


# Main TVDB Class

class TVDB:
    """
    TheTVDB API v4 client for fetching comprehensive TV metadata.

    Provides robust access to TheTVDB API v4 with comprehensive error handling,
    automatic retries, rate limiting, and response caching.
    """

    BASE_URL = "https://api4.thetvdb.com/v4"
    ARTWORK_BASE_URL = "https://artworks.thetvdb.com"
    MAX_RETRIES = 3
    RETRY_BACKOFF_FACTOR = 2.0
    DEFAULT_TIMEOUT = 30
    RATE_LIMIT_WINDOW = 60
    MAX_REQUESTS_PER_WINDOW = 100

    def __init__(
        self,
        api_key: str,
        pin: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        enable_caching: bool = True,
        cache_ttl: int = 3600,
    ) -> None:
        """
        Initialize TVDB API client.

        Args:
            api_key: TVDB API key
            pin: Optional subscriber PIN for enhanced access
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            enable_caching: Whether to enable response caching
            cache_ttl: Cache time-to-live in seconds
        """
        self.api_key = api_key
        self.pin = pin
        self.timeout = ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.enable_caching = enable_caching
        self.cache_ttl = cache_ttl

        # Authentication state
        self.bearer_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None

        # Rate limiting
        self.request_timestamps: List[float] = []

        # Response caching
        self.cache: Dict[str, Tuple[Dict, datetime]] = {}

        # Session management
        self.session: Optional[ClientSession] = None

        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.logger.debug(f"TVDbv4 API initialized successfully")
    async def __aenter__(self) -> TVDB:
        """Async context manager entry."""
        await self._ensure_session()
        # Authentication will be handled lazily when needed by _make_request
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self) -> None:
        """Ensure aiohttp session is created."""
        if self.session is None or self.session.closed:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=10,
                ttl_dns_cache=300,
                use_dns_cache=True,
            )
            self.session = ClientSession(
                timeout=self.timeout,
                connector=connector,
                headers={"User-Agent": "JellyfinNotificationBot/1.0"}
            )

    async def close(self) -> None:
        """Close the client session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def _clean_old_cache_entries(self) -> None:
        """Remove expired cache entries."""
        now = datetime.now(timezone.utc)
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if now - timestamp > timedelta(seconds=self.cache_ttl)
        ]
        for key in expired_keys:
            del self.cache[key]

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Get data from cache if valid."""
        if not self.enable_caching:
            return None

        if cache_key in self.cache:
            data, timestamp = self.cache[cache_key]
            if datetime.now(timezone.utc) - timestamp < timedelta(seconds=self.cache_ttl):
                self.logger.debug(f"Cache hit for key: {cache_key}")
                return data
            else:
                del self.cache[cache_key]

        return None

    def _store_in_cache(self, cache_key: str, data: Dict) -> None:
        """Store data in cache."""
        if self.enable_caching:
            self.cache[cache_key] = (data, datetime.now(timezone.utc))
            if len(self.cache) % 50 == 0:
                self._clean_old_cache_entries()

    async def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting."""
        now = time.time()

        self.request_timestamps = [
            ts for ts in self.request_timestamps
            if now - ts < self.RATE_LIMIT_WINDOW
        ]

        if len(self.request_timestamps) >= self.MAX_REQUESTS_PER_WINDOW:
            wait_time = self.RATE_LIMIT_WINDOW - (now - self.request_timestamps[0])
            if wait_time > 0:
                self.logger.warning(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)

        self.request_timestamps.append(now)

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        require_auth: bool = True,
    ) -> Dict:
        """
        Make HTTP request with comprehensive error handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: URL parameters
            data: Request body data
            require_auth: Whether authentication is required

        Returns:
            Response data as dictionary

        Raises:
            TVDBAPIError: For various API error conditions
        """
        await self._ensure_session()
        await self._check_rate_limit()

        if require_auth and not await self._is_authenticated():
            await self.authenticate()

        url = urljoin(self.BASE_URL, endpoint.lstrip('/'))
        headers = {}

        if require_auth and self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        cache_key = f"{method}:{url}:{str(params)}"
        if method.upper() == "GET":
            cached_data = self._get_from_cache(cache_key)
            if cached_data:
                return cached_data

        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                self.logger.debug(f"Making request: {method} {url} (attempt {attempt + 1})")

                async with self.session.request(
                    method,
                    url,
                    params=params,
                    json=data,
                    headers=headers
                ) as response:

                    if response.status == 200:
                        response_data = await response.json()
                        
                        # Debug logging to understand response structure
                        self.logger.debug(f"TVDb raw response type: {type(response_data)}")
                        if isinstance(response_data, dict):
                            self.logger.debug(f"TVDb response keys: {list(response_data.keys())[:10]}")  # First 10 keys
                            # Log data structure if present
                            if 'data' in response_data:
                                data_item = response_data['data']
                                if isinstance(data_item, dict):
                                    self.logger.debug(f"  - data keys: {list(data_item.keys())[:10]}")
                                    self.logger.debug(f"  - id: {data_item.get('id', 'NOT FOUND')}")
                                    self.logger.debug(f"  - name: {data_item.get('name', 'NOT FOUND')}")
                                    self.logger.debug(f"  - score: {data_item.get('score', 'NOT FOUND')}")
                                    self.logger.debug(f"  - averageRuntime: {data_item.get('averageRuntime', 'NOT FOUND')}")
                                elif isinstance(data_item, list) and len(data_item) > 0:
                                    self.logger.debug(f"  - data is array with {len(data_item)} items")
                                    if isinstance(data_item[0], dict):
                                        self.logger.debug(f"  - first item keys: {list(data_item[0].keys())[:10]}")

                        if method.upper() == "GET":
                            self._store_in_cache(cache_key, response_data)

                        return response_data

                    elif response.status == 401:
                        error_data = await response.json() if response.content_type == 'application/json' else {}
                        raise TVDBAuthenticationError(
                            f"Authentication failed: {error_data.get('Error', 'Invalid credentials')}",
                            status_code=response.status,
                            response_data=error_data
                        )

                    elif response.status == 404:
                        error_data = await response.json() if response.content_type == 'application/json' else {}
                        raise TVDBNotFoundError(
                            f"Resource not found: {error_data.get('Error', 'Not found')}",
                            status_code=response.status,
                            response_data=error_data
                        )

                    elif response.status == 429:
                        retry_after = int(response.headers.get('Retry-After', 60))
                        error_data = await response.json() if response.content_type == 'application/json' else {}
                        raise TVDBRateLimitError(
                            f"Rate limit exceeded: {error_data.get('Error', 'Too many requests')}",
                            status_code=response.status,
                            response_data=error_data,
                            retry_after=retry_after
                        )

                    elif 500 <= response.status < 600:
                        error_data = await response.json() if response.content_type == 'application/json' else {}
                        raise TVDBServerError(
                            f"Server error: {error_data.get('Error', 'Internal server error')}",
                            status_code=response.status,
                            response_data=error_data
                        )

                    else:
                        error_data = await response.json() if response.content_type == 'application/json' else {}
                        raise TVDBAPIError(
                            f"API error: {error_data.get('Error', f'HTTP {response.status}')}",
                            status_code=response.status,
                            response_data=error_data
                        )

            except TVDBRateLimitError as e:
                if attempt < self.max_retries:
                    wait_time = e.retry_after
                    self.logger.warning(f"Rate limited, waiting {wait_time} seconds before retry")
                    await asyncio.sleep(wait_time)
                    last_exception = e
                    continue
                else:
                    raise e

            except (TVDBAuthenticationError, TVDBNotFoundError) as e:
                raise e

            except (ClientError, asyncio.TimeoutError, TVDBServerError) as e:
                if attempt < self.max_retries:
                    wait_time = self.RETRY_BACKOFF_FACTOR ** attempt
                    self.logger.warning(f"Request failed, retrying in {wait_time:.2f} seconds: {e}")
                    await asyncio.sleep(wait_time)
                    last_exception = e
                    continue
                else:
                    if isinstance(e, (ClientError, asyncio.TimeoutError)):
                        raise TVDBAPIError(f"Network error after {self.max_retries} retries: {e}")
                    else:
                        raise e

            except Exception as e:
                self.logger.error(f"Unexpected error in API request: {e}")
                raise TVDBAPIError(f"Unexpected error: {e}")

        if last_exception:
            raise last_exception
        else:
            raise TVDBAPIError("Request failed after all retries")

    async def _is_authenticated(self) -> bool:
        """Check if we have a valid authentication token."""
        if not self.bearer_token:
            return False

        if self.token_expires_at and datetime.now(timezone.utc) >= self.token_expires_at:
            self.logger.info("Bearer token expired, need to re-authenticate")
            return False

        return True

    async def authenticate(self) -> None:
        """
        Authenticate with TVDB API and obtain bearer token.

        This method handles authentication with the TVDB API v4. It supports both
        standard API key authentication and subscriber authentication with PIN.

        The authentication token is valid for approximately 30 days, after which
        it will be automatically renewed.

        Raises:
            TVDBAuthenticationError: If authentication fails
        """
        auth_data = {"apikey": self.api_key}
        if self.pin:
            auth_data["pin"] = self.pin

        try:
            # Note: Authentication endpoint doesn't require auth header
            response_data = await self._make_request(
                "POST",
                "/login",
                data=auth_data,
                require_auth=False
            )

            if "data" in response_data and "token" in response_data["data"]:
                self.bearer_token = response_data["data"]["token"]
                # Token expires in 30 days, but we'll refresh after 28 for safety
                self.token_expires_at = datetime.now(timezone.utc) + timedelta(days=28)

                access_mode = "subscriber" if self.pin else "standard"
                self.logger.info(f"Successfully authenticated with TVDB API ({access_mode} mode)")
            else:
                raise TVDBAuthenticationError("No token received in authentication response")

        except TVDBAPIError:
            raise
        except Exception as e:
            raise TVDBAuthenticationError(f"Authentication failed: {e}")

    def _parse_artwork(self, artwork_data: List[Dict]) -> List[TVDBArtwork]:
        """Parse artwork data from API response."""
        artworks = []
        for art_dict in artwork_data or []:
            try:
                artwork = TVDBArtwork(
                    id=art_dict.get("id"),
                    image=art_dict.get("image"),
                    thumbnail=art_dict.get("thumbnail"),
                    type=art_dict.get("type"),
                    width=art_dict.get("width"),
                    height=art_dict.get("height"),
                    includes_text=art_dict.get("includesText"),
                    language=art_dict.get("language"),
                    score=art_dict.get("score")
                )
                artworks.append(artwork)
            except Exception as e:
                self.logger.warning(f"Failed to parse artwork data: {e}")
        return artworks

    def _parse_characters(self, character_data: List[Dict]) -> List[TVDBCharacter]:
        """Parse character data from API response."""
        characters = []
        for char_dict in character_data or []:
            try:
                character = TVDBCharacter(
                    id=char_dict.get("id"),
                    name=char_dict.get("name"),
                    person_name=char_dict.get("personName"),
                    person_image=char_dict.get("personImgURL"),
                    episode_id=char_dict.get("episodeId"),
                    series_id=char_dict.get("seriesId"),
                    movie_id=char_dict.get("movieId"),
                    is_featured=char_dict.get("isFeatured"),
                    sort_order=char_dict.get("sort"),
                    role=char_dict.get("role")
                )
                characters.append(character)
            except Exception as e:
                self.logger.warning(f"Failed to parse character data: {e}")
        return characters

    def _parse_companies(self, company_data: List[Dict]) -> List[TVDBCompany]:
        """Parse company data from API response."""
        companies = []
        for comp_dict in company_data or []:
            try:
                company = TVDBCompany(
                    id=comp_dict.get("id"),
                    name=comp_dict.get("name"),
                    slug=comp_dict.get("slug"),
                    name_translations=comp_dict.get("nameTranslations", []),
                    overview_translations=comp_dict.get("overviewTranslations", []),
                    aliases=comp_dict.get("aliases", []),
                    country=comp_dict.get("country"),
                    primary_company_type=comp_dict.get("primaryCompanyType"),
                    active_date=comp_dict.get("activeDate"),
                    inactive_date=comp_dict.get("inactiveDate"),
                    tags=comp_dict.get("tags", [])
                )
                companies.append(company)
            except Exception as e:
                self.logger.warning(f"Failed to parse company data: {e}")
        return companies

    async def get_series_metadata(self, tvdb_id: int) -> Optional[TVDBSeriesMetadata]:
        """
        Fetch comprehensive series metadata from TVDB.

        Args:
            tvdb_id: TVDB series ID

        Returns:
            TVDBSeriesMetadata object or None if not found
        """
        try:
            self.logger.debug("=" * 60)
            self.logger.debug(f"📺 TVDb API: Fetching series metadata for ID: {tvdb_id}")
            self.logger.debug("=" * 60)
            
            response = await self._make_request("GET", f"/series/{tvdb_id}")
            series_data = response.get("data", {})
            
            self.logger.debug("📦 Basic series response received:")
            self.logger.debug(f"  Response keys: {list(response.keys())}")
            self.logger.debug(f"  Data keys: {list(series_data.keys()) if series_data else 'No data'}")
            
            if series_data:
                self.logger.debug(f"  Series name: {series_data.get('name', 'N/A')}")
                self.logger.debug(f"  Series ID: {series_data.get('id', 'N/A')}")
                self.logger.debug(f"  Overview: {(series_data.get('overview', 'N/A')[:100] + '...') if series_data.get('overview') and len(series_data.get('overview', '')) > 100 else series_data.get('overview', 'N/A')}")
                self.logger.debug(f"  Status: {series_data.get('status', 'N/A')}")
                self.logger.debug(f"  First aired: {series_data.get('firstAired', 'N/A')}")

            extended_response = await self._make_request("GET", f"/series/{tvdb_id}/extended")
            extended_data = extended_response.get("data", {})
            
            self.logger.debug("📦 Extended series response received:")
            self.logger.debug(f"  Extended data keys: {list(extended_data.keys()) if extended_data else 'No data'}")

            series_data.update(extended_data)

            metadata = TVDBSeriesMetadata(
                tvdb_id=series_data.get("id"),
                name=series_data.get("name"),
                slug=series_data.get("slug"),
                overview=series_data.get("overview"),
                original_country=series_data.get("originalCountry"),
                original_language=series_data.get("originalLanguage"),
                default_season_type=series_data.get("defaultSeasonType"),
                status=series_data.get("status", {}).get("name") if series_data.get("status") else None,
                first_aired=series_data.get("firstAired"),
                last_aired=series_data.get("lastAired"),
                next_aired=series_data.get("nextAired"),
                score=series_data.get("score"),
                rating=series_data.get("rating"),
                rating_count=series_data.get("ratingCount"),
                average_runtime=series_data.get("averageRuntime"),
                is_order_randomized=series_data.get("isOrderRandomized"),
                name_translations=series_data.get("nameTranslations", []),
                overview_translations=series_data.get("overviewTranslations", []),
                alias_translations=series_data.get("aliasTranslations", []),
                genres=[g.get("name") for g in series_data.get("genres", []) if g.get("name")],
                tags=[t.get("name") for t in series_data.get("tags", []) if t.get("name")],
                companies=self._parse_companies(series_data.get("companies", [])),
                characters=self._parse_characters(series_data.get("characters", [])),
                artworks=self._parse_artwork(series_data.get("artworks", [])),
                last_updated=series_data.get("lastUpdated"),
                year=series_data.get("year")
            )

            for artwork in metadata.artworks:
                if artwork.type == 2:  # Poster
                    metadata.poster_url = f"{self.ARTWORK_BASE_URL}{artwork.image}"
                elif artwork.type == 1:  # Banner
                    metadata.banner_url = f"{self.ARTWORK_BASE_URL}{artwork.image}"
                elif artwork.type == 3:  # Fanart
                    metadata.fanart_url = f"{self.ARTWORK_BASE_URL}{artwork.image}"

            # Log the final metadata object
            self.logger.debug("=" * 60)
            self.logger.debug("✅ TVDb METADATA OBJECT CREATED")
            self.logger.debug("=" * 60)
            self.logger.debug(f"  TVDb ID: {metadata.tvdb_id}")
            self.logger.debug(f"  Name: {metadata.name}")
            self.logger.debug(f"  Overview: {(metadata.overview[:100] + '...') if metadata.overview and len(metadata.overview) > 100 else metadata.overview}")
            self.logger.debug(f"  Status: {metadata.status}")
            self.logger.debug(f"  First Aired: {metadata.first_aired}")
            self.logger.debug(f"  Rating: {metadata.rating}")
            self.logger.debug(f"  Rating Count: {metadata.rating_count}")
            self.logger.debug(f"  Average Runtime: {metadata.average_runtime}")
            self.logger.debug(f"  Genres: {metadata.genres}")
            self.logger.debug(f"  Poster URL: {metadata.poster_url}")
            self.logger.debug(f"  Banner URL: {metadata.banner_url}")
            self.logger.debug(f"  Fanart URL: {metadata.fanart_url}")
            self.logger.debug(f"  Number of artworks: {len(metadata.artworks)}")
            self.logger.debug("=" * 60)

            self.logger.info(f"Successfully fetched series metadata for TVDB ID: {tvdb_id}")
            return metadata

        except TVDBNotFoundError:
            self.logger.warning(f"Series not found in TVDB: {tvdb_id}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to fetch series metadata for {tvdb_id}: {e}")
            return None

    async def get_season_metadata(self, season_id: int) -> Optional[TVDBSeasonMetadata]:
        """
        Fetch comprehensive season metadata from TVDB.

        Args:
            season_id: TVDB season ID

        Returns:
            TVDBSeasonMetadata object or None if not found
        """
        try:
            response = await self._make_request("GET", f"/seasons/{season_id}")
            season_data = response.get("data", {})

            extended_response = await self._make_request("GET", f"/seasons/{season_id}/extended")
            extended_data = extended_response.get("data", {})

            season_data.update(extended_data)

            season_type = None
            if season_data.get("type"):
                season_type = TVDBSeasonType(
                    id=season_data["type"].get("id"),
                    name=season_data["type"].get("name"),
                    type=season_data["type"].get("type"),
                    alt_name=season_data["type"].get("alternateName")
                )

            metadata = TVDBSeasonMetadata(
                tvdb_id=season_data.get("id"),
                series_id=season_data.get("seriesId"),
                name=season_data.get("name"),
                number=season_data.get("number"),
                overview=season_data.get("overview"),
                image=f"{self.ARTWORK_BASE_URL}{season_data['image']}" if season_data.get("image") else None,
                image_type=season_data.get("imageType"),
                year=season_data.get("year"),
                season_type=season_type,
                name_translations=season_data.get("nameTranslations", []),
                overview_translations=season_data.get("overviewTranslations", []),
                companies=self._parse_companies(season_data.get("companies", [])),
                artworks=self._parse_artwork(season_data.get("artworks", [])),
                last_updated=season_data.get("lastUpdated")
            )

            self.logger.info(f"Successfully fetched season metadata for TVDB ID: {season_id}")
            return metadata

        except TVDBNotFoundError:
            self.logger.warning(f"Season not found in TVDB: {season_id}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to fetch season metadata for {season_id}: {e}")
            return None

    async def get_episode_metadata(self, episode_id: int) -> Optional[TVDBEpisodeMetadata]:
        """
        Fetch comprehensive episode metadata from TVDB.

        Args:
            episode_id: TVDB episode ID

        Returns:
            TVDBEpisodeMetadata object or None if not found
        """
        try:
            response = await self._make_request("GET", f"/episodes/{episode_id}")
            episode_data = response.get("data", {})

            extended_response = await self._make_request("GET", f"/episodes/{episode_id}/extended")
            extended_data = extended_response.get("data", {})

            episode_data.update(extended_data)

            metadata = TVDBEpisodeMetadata(
                tvdb_id=episode_data.get("id"),
                series_id=episode_data.get("seriesId"),
                season_id=episode_data.get("seasonId"),
                name=episode_data.get("name"),
                overview=episode_data.get("overview"),
                image=f"{self.ARTWORK_BASE_URL}{episode_data['image']}" if episode_data.get("image") else None,
                image_type=episode_data.get("imageType"),
                number=episode_data.get("number"),
                absolute_number=episode_data.get("absoluteNumber"),
                season_number=episode_data.get("seasonNumber"),
                aired_order=episode_data.get("airedOrder"),
                dvd_order=episode_data.get("dvdOrder"),
                aired=episode_data.get("aired"),
                runtime=episode_data.get("runtime"),
                production_code=episode_data.get("productionCode"),
                finale_type=episode_data.get("finaleType"),
                rating=episode_data.get("rating"),
                rating_count=episode_data.get("ratingCount"),
                is_movie=episode_data.get("isMovie"),
                name_translations=episode_data.get("nameTranslations", []),
                overview_translations=episode_data.get("overviewTranslations", []),
                characters=self._parse_characters(episode_data.get("characters", [])),
                artworks=self._parse_artwork(episode_data.get("artworks", [])),
                companies=self._parse_companies(episode_data.get("companies", [])),
                tags=[t.get("name") for t in episode_data.get("tags", []) if t.get("name")],
                nominations=episode_data.get("nominations", []),
                last_updated=episode_data.get("lastUpdated"),
                year=episode_data.get("year")
            )

            self.logger.info(f"Successfully fetched episode metadata for TVDB ID: {episode_id}")
            return metadata

        except TVDBNotFoundError:
            self.logger.warning(f"Episode not found in TVDB: {episode_id}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to fetch episode metadata for {episode_id}: {e}")
            return None

    async def find_season_metadata(self, series_tvdb_id: int, season_number: Optional[int]) -> Optional[TVDBSeasonMetadata]:
        """
        Find season metadata by series ID and season number.

        Args:
            series_tvdb_id: TVDB series ID
            season_number: Season number

        Returns:
            TVDBSeasonMetadata if found, None otherwise
        """
        if not season_number:
            return None

        try:
            response = await self._make_request("GET", f"/series/{series_tvdb_id}/seasons/default")
            seasons_data = response.get("data", {}).get("seasons", [])

            for season_data in seasons_data:
                if season_data.get("number") == season_number:
                    season_id = season_data.get("id")
                    if season_id:
                        return await self.get_season_metadata(season_id)

            self.logger.warning(f"Season {season_number} not found for series {series_tvdb_id}")
            return None

        except Exception as e:
            self.logger.error(f"Error finding season metadata: {e}")
            return None

    async def find_episode_metadata(
        self,
        series_tvdb_id: int,
        season_number: Optional[int],
        episode_number: Optional[int]
    ) -> Optional[TVDBEpisodeMetadata]:
        """
        Find episode metadata by series ID, season number, and episode number.

        Args:
            series_tvdb_id: TVDB series ID
            season_number: Season number
            episode_number: Episode number

        Returns:
            TVDBEpisodeMetadata if found, None otherwise
        """
        if not season_number or not episode_number:
            return None

        try:
            page = 0
            while page < 10:
                response = await self._make_request(
                    "GET",
                    f"/series/{series_tvdb_id}/episodes/default",
                    params={"page": page}
                )

                episodes_data = response.get("data", {}).get("episodes", [])
                if not episodes_data:
                    break

                for episode_data in episodes_data:
                    if (episode_data.get("seasonNumber") == season_number and
                        episode_data.get("number") == episode_number):
                        episode_id = episode_data.get("id")
                        if episode_id:
                            return await self.get_episode_metadata(episode_id)

                links = response.get("links", {})
                if not links.get("next"):
                    break

                page += 1

            self.logger.warning(
                f"Episode S{season_number:02d}E{episode_number:02d} not found for series {series_tvdb_id}"
            )
            return None

        except Exception as e:
            self.logger.error(f"Error finding episode metadata: {e}")
            return None

    async def search_series(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search for series by name.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of series search results
        """
        try:
            response = await self._make_request(
                "GET",
                "/search",
                params={"query": query, "type": "series", "limit": limit}
            )

            return response.get("data", [])

        except Exception as e:
            self.logger.error(f"Failed to search for series '{query}': {e}")
            return []


# Standalone functions for template integration

async def add_tvdb_metadata_to_item(
    item: Any,
    tvdb_client: TVDB,
    template_context: Optional[Dict] = None
) -> bool:
    """
    Add TVDB metadata to a MediaItem object for template rendering.

    This function adds TVDB metadata directly to the item object,
    making it available in Jinja2 templates. Also sets the attribution
    flag if metadata is successfully added.

    Args:
        item: MediaItem object to enhance
        tvdb_client: Initialized TVDB client
        template_context: Optional template context dict to set attribution flag

    Returns:
        True if metadata was added, False otherwise
    """
    if not hasattr(item, 'item_type') or not hasattr(item, 'tvdb_id'):
        return False

    item_type = getattr(item, 'item_type', '').lower()
    tvdb_id = getattr(item, 'tvdb_id', None)

    if item_type not in ['series', 'season', 'episode'] or not tvdb_id:
        return False

    try:
        tvdb_id_int = int(tvdb_id)
    except (ValueError, TypeError):
        logger.warning(f"Invalid TVDB ID format: {tvdb_id}")
        return False

    try:
        metadata_added = False

        if item_type == 'series':
            metadata = await tvdb_client.get_series_metadata(tvdb_id_int)
            if metadata:
                item.tvdb_series = metadata
                item.tvdb_metadata_type = 'series'
                metadata_added = True

        elif item_type == 'season':
            series_id = getattr(item, 'series_id', None)
            season_number = getattr(item, 'season_number', None)
            if series_id and season_number:
                try:
                    series_id_int = int(series_id)
                    metadata = await tvdb_client.find_season_metadata(series_id_int, season_number)
                    if metadata:
                        item.tvdb_season = metadata
                        item.tvdb_metadata_type = 'season'
                        metadata_added = True
                except (ValueError, TypeError):
                    logger.warning(f"Invalid series ID for season: {series_id}")

        elif item_type == 'episode':
            series_id = getattr(item, 'series_id', None)
            season_number = getattr(item, 'season_number', None)
            episode_number = getattr(item, 'episode_number', None)
            if series_id and season_number and episode_number:
                try:
                    series_id_int = int(series_id)
                    metadata = await tvdb_client.find_episode_metadata(series_id_int, season_number, episode_number)
                    if metadata:
                        item.tvdb_episode = metadata
                        item.tvdb_metadata_type = 'episode'
                        metadata_added = True
                except (ValueError, TypeError):
                    logger.warning(f"Invalid series ID for episode: {series_id}")

        # Mark as enhanced and set attribution flag
        item.has_tvdb_metadata = metadata_added

        if metadata_added and template_context is not None:
            template_context['tvdb_attribution_needed'] = True

        return metadata_added

    except Exception as e:
        logger.error(f"Failed to add TVDB metadata to {item_type} '{getattr(item, 'name', 'unknown')}': {e}")
        item.has_tvdb_metadata = False
        return False


async def add_tvdb_metadata_to_items(
    items: List[Any],
    tvdb_client: TVDB,
    template_context: Optional[Dict] = None
) -> int:
    """
    Add TVDB metadata to multiple MediaItem objects.

    Args:
        items: List of MediaItem objects to enhance
        tvdb_client: Initialized TVDB client
        template_context: Optional template context dict to set attribution flag

    Returns:
        Number of items that were successfully enhanced
    """
    if not items or not tvdb_client:
        return 0

    # Filter items that can benefit from TVDB enhancement
    tv_items = [
        item for item in items
        if hasattr(item, 'item_type') and getattr(item, 'item_type', '').lower() in ['series', 'season', 'episode']
        and hasattr(item, 'tvdb_id') and getattr(item, 'tvdb_id', None)
    ]

    if not tv_items:
        return 0

    logger.info(f"Adding TVDB metadata to {len(tv_items)} TV items")

    enhanced_count = 0
    for item in tv_items:
        try:
            if await add_tvdb_metadata_to_item(item, tvdb_client, template_context):
                enhanced_count += 1
        except Exception as e:
            logger.error(f"Failed to add TVDB metadata to item {getattr(item, 'name', 'unknown')}: {e}")

    if enhanced_count > 0:
        logger.info(f"Successfully enhanced {enhanced_count}/{len(tv_items)} TV items with TVDB metadata")
        if template_context is not None:
            template_context['tvdb_attribution_needed'] = True

    return enhanced_count


def should_use_tvdb_for_item(item: Any) -> bool:
    """
    Determine if an item should be enhanced with TVDB metadata.

    Args:
        item: MediaItem to check

    Returns:
        True if item should be enhanced, False otherwise
    """
    if not hasattr(item, 'item_type') or not hasattr(item, 'tvdb_id'):
        return False

    item_type = getattr(item, 'item_type', '').lower()
    tvdb_id = getattr(item, 'tvdb_id', None)

    return (
        item_type in ['series', 'season', 'episode'] and
        tvdb_id is not None and
        str(tvdb_id).strip() != ''
    )