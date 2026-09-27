from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .models import ProfileName


@dataclass(frozen=True, slots=True)
class EditProfile:
    name: ProfileName
    target_min_seconds: float
    target_max_seconds: float
    default_shot_seconds: float
    human_hold_seconds: float
    ending_hold_seconds: float
    selective_text: bool
    hard_cut_first: bool
    road_reset: bool
    hook_layers: int
    font_family: str
    support_color: str
    keyword_color: str


PROFILES: dict[ProfileName, EditProfile] = {
    "TRAVEL_DOCUMENTARY": EditProfile(
        name="TRAVEL_DOCUMENTARY",
        target_min_seconds=45,
        target_max_seconds=90,
        default_shot_seconds=3.4,
        human_hold_seconds=4.8,
        ending_hold_seconds=6.0,
        selective_text=True,
        hard_cut_first=True,
        road_reset=True,
        hook_layers=3,
        font_family="Montserrat",
        support_color="#F4F1E9",
        keyword_color="#FFC928",
    ),
    "TALKING_HEAD_EXPERT": EditProfile(
        name="TALKING_HEAD_EXPERT",
        target_min_seconds=10,
        target_max_seconds=90,
        default_shot_seconds=4.0,
        human_hold_seconds=5.0,
        ending_hold_seconds=1.0,
        selective_text=True,
        hard_cut_first=True,
        road_reset=False,
        hook_layers=3,
        font_family="Montserrat",
        support_color="#F4F1E9",
        keyword_color="#FFC928",
    ),
    "EXPLAINER_NEWS": EditProfile(
        name="EXPLAINER_NEWS",
        target_min_seconds=30,
        target_max_seconds=90,
        default_shot_seconds=2.8,
        human_hold_seconds=3.5,
        ending_hold_seconds=2.0,
        selective_text=True,
        hard_cut_first=True,
        road_reset=False,
        hook_layers=3,
        font_family="Montserrat",
        support_color="#F4F1E9",
        keyword_color="#FFC928",
    ),
    "DIRECT_RECRUITMENT": EditProfile(
        name="DIRECT_RECRUITMENT",
        target_min_seconds=25,
        target_max_seconds=90,
        default_shot_seconds=3.0,
        human_hold_seconds=4.0,
        ending_hold_seconds=2.0,
        selective_text=True,
        hard_cut_first=True,
        road_reset=False,
        hook_layers=3,
        font_family="Montserrat",
        support_color="#F4F1E9",
        keyword_color="#FFC928",
    ),
}


def get_profile(name: ProfileName) -> EditProfile:
    return PROFILES[name]
