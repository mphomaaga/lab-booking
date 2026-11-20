from app.passwords import hash_password, verify_password


def test_round_trip():
    hashed = hash_password("student-pass-1")
    assert hashed != "student-pass-1"
    assert hashed.startswith("$2")
    assert len(hashed) <= 255
    assert verify_password("student-pass-1", hashed) is True


def test_wrong_password_fails():
    hashed = hash_password("student-pass-1")
    assert verify_password("wrong", hashed) is False
    assert verify_password("", hashed) is False


def test_hashes_are_salted():
    assert hash_password("same") != hash_password("same")


def test_malformed_hash_is_a_failure_not_an_error():
    assert verify_password("anything", "not-a-bcrypt-hash") is False
