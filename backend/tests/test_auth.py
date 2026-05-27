import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    payload = {
        "naziv_klinike": "Nova Ordinacija",
        "email": "new@test.hr",
        "password": "NewPass123!",
        "ime": "Novi",
        "prezime": "Korisnik",
        "terms_accepted": True,
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "new@test.hr"
    assert data["user"]["role"] == "admin"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {
        "naziv_klinike": "Ordinacija 1",
        "email": "dup@test.hr",
        "password": "Pass123!",
        "ime": "Prvi",
        "prezime": "Korisnik",
        "terms_accepted": True,
    }
    resp1 = await client.post("/api/auth/register", json=payload)
    assert resp1.status_code == 201

    payload2 = {**payload, "naziv_klinike": "Ordinacija 2"}
    resp2 = await client.post("/api/auth/register", json=payload2)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    payload = {
        "naziv_klinike": "Bad Email",
        "email": "not-an-email",
        "password": "Pass123!",
        "ime": "Bad",
        "prezime": "Email",
        "terms_accepted": True,
    }
    resp = await client.post("/api/auth/register", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    reg_payload = {
        "naziv_klinike": "Login Test",
        "email": "login@test.hr",
        "password": "LoginPass1!",
        "ime": "Login",
        "prezime": "Test",
        "terms_accepted": True,
    }
    await client.post("/api/auth/register", json=reg_payload)

    login_resp = await client.post("/api/auth/login", json={"email": "login@test.hr", "password": "LoginPass1!"})
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    reg_payload = {
        "naziv_klinike": "Wrong Pass",
        "email": "wrongpass@test.hr",
        "password": "CorrectPass1!",
        "ime": "Wrong",
        "prezime": "Pass",
        "terms_accepted": True,
    }
    await client.post("/api/auth/register", json=reg_payload)

    resp = await client.post("/api/auth/login", json={"email": "wrongpass@test.hr", "password": "BadPassword!"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    resp = await client.post("/api/auth/login", json={"email": "nobody@test.hr", "password": "SomePass1!"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_success(client: AsyncClient, auth_headers: dict[str, str]):
    # Get tokens from login
    login_resp = await client.post("/api/auth/login", json={"email": "admin@test.hr", "password": "Test1234!"})
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["refresh_token"] != refresh_token  # rotation


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient):
    resp = await client.post("/api/auth/refresh", json={"refresh_token": "invalid-token-here"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_success(client: AsyncClient, auth_headers: dict[str, str]):
    login_resp = await client.post("/api/auth/login", json={"email": "admin@test.hr", "password": "Test1234!"})
    refresh_token = login_resp.json()["refresh_token"]

    resp = await client.post("/api/auth/logout", json={"refresh_token": refresh_token})
    assert resp.status_code == 204

    # Refreshing with same token should fail
    refresh_resp = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "admin@test.hr"
    assert data["role"] == "admin"
    assert "tenant" in data


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
