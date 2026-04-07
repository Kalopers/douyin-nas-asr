# -*- coding: utf-8 -*-
# @Date     : 2026/04/08
# @Author   : Codex
# @File     : types.py
# @Desc     : ASR 抽象层结果对象

from typing import List, Optional

from pydantic import BaseModel, Field


class TranscriptionSegment(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    text: str


class TranscriptionResult(BaseModel):
    text: str
    backend: str
    model: str
    segments: List[TranscriptionSegment] = Field(default_factory=list)
