import jwt
import pytest
from fastapi import HTTPException
from cryptography.hazmat.primitives.asymmetric import ec
from app import auth
from app.config import settings


def test_valid_supabase_asymmetric_token_and_wrong_role(monkeypatch):
    key=ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv('SUPABASE_URL','https://example.supabase.co')
    settings.cache_clear()
    class JWKS:
        def get_signing_key_from_jwt(self, token):
            return type('SigningKey',(),{'key':key.public_key()})()
    monkeypatch.setattr(auth,'jwks_client',lambda:JWKS())
    claims={'sub':'user-a','role':'authenticated','aud':'authenticated','iss':'https://example.supabase.co/auth/v1','exp':4102444800}
    token=jwt.encode(claims,key,algorithm='ES256')
    assert auth.current_user('Bearer '+token)=='user-a'
    with pytest.raises(HTTPException) as exc:
        auth.current_user('Bearer '+jwt.encode({**claims,'role':'anon'},key,algorithm='ES256'))
    assert exc.value.status_code==401
    settings.cache_clear()
