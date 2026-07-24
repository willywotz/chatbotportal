"""Tests for app.utils.clean_agency_ids."""
from app.utils import clean_agency_ids


def test_passes_clean_list_through():
    assert clean_agency_ids(["a", "b"]) == ["a", "b"]


def test_splits_comma_joined_element():
    assert clean_agency_ids(["id1,id2,id3"]) == ["id1", "id2", "id3"]


def test_trims_whitespace_and_drops_blanks():
    assert clean_agency_ids([" id1 ", "", "id2, ,id3"]) == ["id1", "id2", "id3"]


def test_none_yields_empty_list():
    assert clean_agency_ids(None) == []


def test_stringifies_non_str_elements():
    assert clean_agency_ids([123]) == ["123"]
