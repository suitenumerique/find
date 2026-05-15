"""Models for find's core app"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """User for the find application"""
