"""Делает пакет `recognizer` импортируемым в тестах (cv/ на sys.path)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
