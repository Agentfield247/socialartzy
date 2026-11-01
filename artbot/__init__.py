"""SocialArtzy - a free, cloud-run Instagram + Pinterest posting bot for artists.

The package holds the reusable pieces (configuration, logging, queue handling,
rate limiting and the shared posting loop). The two platform scripts
``post_instagram.py`` and ``post_pinterest.py`` live in the repository root so
they can also be run on their own.
"""

__version__ = "1.0.0"