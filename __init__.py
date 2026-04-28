"""Affective Core - Agent 情感框架 MVP v1.0"""

__version__ = "1.0.0"
__author__ = "Luciana & Kimi Claw & Miko"

# 支持作为包导入和直接运行两种方式
try:
    from .emotion_engine import AffectiveCore
except ImportError:
    from emotion_engine import AffectiveCore

__all__ = ["AffectiveCore"]
