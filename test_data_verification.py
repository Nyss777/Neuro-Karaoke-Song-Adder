import sys
from datetime import date

import pytest

sys.path.append(r'C:\Users\Nyss\Documents\Code\Python\Neuro_karaoke\utils\my_tools')

from data_verification import (
    ValidationError,
    _validate_version_in_timeframe,
    validate_payload,
)


# A "Base" valid payload we can modify for specific tests
@pytest.fixture
def valid_payload():
    return {
        'disc_number': '1',
        'track': '1/98',
        'date': '2023-01-03',
        'version': '1.2',
        'cover_artist': 'Neuro & Evil',
        'special': '0'
    }

# --- TEST VALID CASE ---
def test_valid_payload(valid_payload):
    assert validate_payload(valid_payload) is True

# --- TEST DISC NUMBER ---
@pytest.mark.parametrize("disc", ['1', '9', '66'])
def test_valid_disc_numbers(valid_payload, disc):
    valid_payload['disc_number'] = disc
    assert validate_payload(valid_payload) is True

@pytest.mark.parametrize("disc", ['0', '10', '99', ''])
def test_invalid_disc_numbers(valid_payload, disc):
    valid_payload['disc_number'] = disc
    with pytest.raises(ValidationError):
        validate_payload(valid_payload)

# --- TEST TRACKS ---
@pytest.mark.parametrize("track", ['1/1', '98/98', '5/10', "70"])
def test_valid_tracks(valid_payload, track):
    valid_payload['track'] = track
    assert validate_payload(valid_payload) is True

@pytest.mark.parametrize("track", ['0/10', '10/5', '1/0', 'abc', '', '0'])
def test_invalid_tracks(valid_payload, track):
    valid_payload['track'] = track
    with pytest.raises(ValidationError):
        validate_payload(valid_payload)

# --- TEST DATES ---
@pytest.mark.parametrize("date", ['2024-06-07', '2023-01-03', str(date.today())])
def test_valid_date(valid_payload, date):
    valid_payload['date'] = date
    assert validate_payload(valid_payload) is True

@pytest.mark.parametrize("date", ['2012-05-07', '2027-01-01', '01-07-2024',
                                  '2026-1-1', "2025-02-30", "foobar"])
def test_invalid_date(valid_payload, date):
    valid_payload['date'] = date
    with pytest.raises(ValidationError):
        validate_payload(valid_payload)

# --- TEST VERSION ---
@pytest.mark.parametrize("ver", ['1', '2.2', '3.4'])
def test_valid_versions(valid_payload, ver):
    valid_payload['version'] = ver
    assert validate_payload(valid_payload) is True

@pytest.mark.parametrize("ver", ["1.1", "2,3", "foobar"])
def test_invalid_versions(valid_payload, ver):
    valid_payload['version'] = ver
    with pytest.raises(ValidationError):
        validate_payload(valid_payload)


# --- TEST COMPLEX VERSIONING VALIDATION ---
@pytest.mark.parametrize("artist, version, input_date", [
    ("Evil", "1", date(2020, 1, 1)),      # Should pass: Artist isn't Neuro
    ("Neuro & Evil", "2", date(2024, 2, 15)),      # Should pass: Artist isn't "Neuro"
    ("Neuro", "1", date(2023, 1, 4)),    # Should pass: Within V1 range
    ("Neuro", "2", date(2023, 5, 28)),   # Should pass: Within V2 range
    ("Neuro", "3", date(2024, 1, 1)),    # Should pass: Within V3 range
])
def test_version_timeframe_success(artist, version, input_date):
    payload = {"cover_artist": artist}
    # If no ValidationError is raised, the test passes
    _validate_version_in_timeframe(payload, version, input_date)

# --- FAILURE CASES ---
@pytest.mark.parametrize("version, input_date, expected_error", [
    # Neuro V1 failures
    ("1", date(2024, 1, 1), "Neuro V1 ended 2023-05-17!"),
    
    # Neuro V2 failures
    ("2", date(2023, 1, 1), "Neuro V2 ended 2023-06-08!"),
    ("2", date(2023, 7, 1), "Neuro V2 ended 2023-06-08!"),
    
    # Neuro V3 failures
    ("3", date(2022, 1, 1), "Neuro V3 started 2023-06-21!"),
])

def test_version_timeframe_failures(version, input_date, expected_error):
    payload = {"cover_artist": "Neuro"}
    
    # We check that it raises an ValidationError AND that the message is correct
    with pytest.raises(ValidationError, match=expected_error):
        _validate_version_in_timeframe(payload, version, input_date)


# --- TEST SPECIAL RULES ---
def test_wrong_twin_order(valid_payload):
    valid_payload['cover_artist'] = "Evil & Neuro"
    with pytest.raises(ValidationError, match="Wrong twin order!"):
        validate_payload(valid_payload)